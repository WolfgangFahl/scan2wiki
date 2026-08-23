"""
Created on 2026-08-23

tests for the standard grid geometry of cam2web

The standard grid is the unrotated full view unit square. All
magnify state lives on it: display rotation is a pure view
transform applied only at the edges (mouse input, overlay drawing)
and the camera's zoom position command is a measured linear
response per axis. The tests therefore check three separable
concerns:
- Rotation is a lossless view transform (issues 38 and 39)
- Window keeps the magnifying frame inside the grid
- Axis/Calibration reproduce the measured camera response and
  report the clamped position the camera actually takes (issue 41)

see https://github.com/WolfgangFahl/scan2wiki/issues/38
https://github.com/WolfgangFahl/scan2wiki/issues/39
https://github.com/WolfgangFahl/scan2wiki/issues/41

@author: wf
"""

from ngwidgets.basetest import Basetest

from scan.camera import CameraCalibrations
from scan.geometry import Axis, Grid, Rotation, Window

# corners of the unit square by name - rotating the square must
# permute these corners, which is readable without any arithmetic
TOP_LEFT = (0.0, 0.0)
TOP_RIGHT = (1.0, 0.0)
BOTTOM_RIGHT = (1.0, 1.0)
BOTTOM_LEFT = (0.0, 1.0)

# an example axis with round numbers for readable expectations:
# command = 1000 * fraction + 100, honored up to command 700 -
# so fractions 0.0 .. 0.6 are reachable and larger ones clamp
EXAMPLE_AXIS = Axis(scale=1000.0, offset=100.0, cmd_max=700)


class TestGeometry(Basetest):
    """
    test the standard grid coordinate handling
    """

    def setUp(self):
        Basetest.setUp(self, debug=False, profile=True)
        # the shipped ruler-scene calibration of the Canon EOS 1000D
        # (see scan2wiki_examples/cameras.yaml) - used to test the
        # measured camera response instead of invented numbers
        calibrations = CameraCalibrations.get_instance()
        self.eos1000d = calibrations.cameras["Canon EOS 1000D"]

    def test_rotation_round_trip(self):
        """
        to_display and to_sensor must be exact inverses for every
        quarter turn - otherwise a click would move the magnifying
        frame to a different sensor area on each rotated view
        """
        points = [TOP_LEFT, TOP_RIGHT, BOTTOM_RIGHT, BOTTOM_LEFT, (0.25, 0.5)]
        for degrees in (0, 90, 180, 270):
            rotation = Rotation(degrees)
            for sx, sy in points:
                dx, dy = rotation.to_display(sx, sy)
                rx, ry = rotation.to_sensor(dx, dy)
                self.assertAlmostEqual(sx, rx, msg=f"rotation {degrees}")
                self.assertAlmostEqual(sy, ry, msg=f"rotation {degrees}")

    def test_rotation_moves_corners(self):
        """
        a clockwise quarter turn must carry each corner to the next
        corner clockwise - the most readable statement of what
        "clockwise display rotation" means
        """
        corner_cycle = [TOP_LEFT, TOP_RIGHT, BOTTOM_RIGHT, BOTTOM_LEFT]
        for index, corner in enumerate(corner_cycle):
            expected = corner_cycle[(index + 1) % 4]
            displayed = Rotation(90).to_display(*corner)
            self.assertEqual(expected, displayed, msg=f"corner {corner}")

    def test_turn(self):
        """
        turn steps the rotation in signed degrees and wraps at 360 -
        the rotate buttons of the UI call this
        """
        rotation = Rotation()
        self.assertEqual(90, rotation.turn(90))
        self.assertEqual(0, rotation.turn(-90))
        self.assertEqual(270, rotation.turn(-90))
        # 90 and 270 exchange the axes, 0 and 180 keep them
        self.assertTrue(rotation.swaps_axes)
        self.assertFalse(Rotation(180).swaps_axes)

    def test_box_to_display(self):
        """
        a rotated axis aligned box must equal the box spanned by its
        rotated corners - this is how the magnifying frame overlay
        is drawn on the rotated view
        """
        box = (0.1, 0.2, 0.3, 0.4)
        for degrees in (0, 90, 180, 270):
            rotation = Rotation(degrees)
            x0, y0, width, height = rotation.box_to_display(*box)
            corners = [
                rotation.to_display(box[0], box[1]),
                rotation.to_display(box[0] + box[2], box[1] + box[3]),
            ]
            xs = [c[0] for c in corners]
            ys = [c[1] for c in corners]
            self.assertAlmostEqual(min(xs), x0, msg=f"rotation {degrees}")
            self.assertAlmostEqual(min(ys), y0, msg=f"rotation {degrees}")
            self.assertAlmostEqual(max(xs) - min(xs), width, msg=f"rotation {degrees}")
            self.assertAlmostEqual(max(ys) - min(ys), height, msg=f"rotation {degrees}")

    def test_window_clamping(self):
        """
        the window center may be commanded anywhere on the unit
        square but the window box must stay fully inside it - a
        center in a corner yields a box touching that corner
        """
        window = Window(width=0.1, height=0.1)
        window.move_to(*TOP_LEFT)
        x0, y0, width, height = window.box()
        self.assertEqual((0.0, 0.0), (x0, y0))
        self.assertAlmostEqual(window.width, width)
        self.assertAlmostEqual(window.height, height)
        # a center commanded outside the grid is clamped onto it
        window.move_to(1.5, -0.5)
        self.assertEqual((1.0, 0.0), (window.cx, window.cy))
        x0, y0, _, _ = window.box()
        self.assertAlmostEqual(1.0 - window.width, x0)
        self.assertEqual(0.0, y0)
        self.assertTrue(window.contains(1.0 - window.width / 2, window.height / 2))
        self.assertFalse(window.contains(0.5, 0.5))

    def test_axis_response(self):
        """
        Axis models the measured camera response command =
        scale * fraction + offset with clamping to the honored band
        [offset, cmd_max] - checked with the round numbers of
        EXAMPLE_AXIS so every expectation is mental arithmetic
        """
        axis = EXAMPLE_AXIS
        # fraction 0 sits at the offset, fraction 0.5 mid range
        self.assertEqual(100, axis.to_command(0.0))
        self.assertEqual(600, axis.to_command(0.5))
        # beyond the honored band the command clamps ...
        self.assertEqual(700, axis.to_command(0.9))
        self.assertEqual(100, axis.to_command(-0.2))
        # ... and to_fraction reports the clamped position so the
        # drawn frame matches the actual window
        self.assertAlmostEqual(0.6, axis.to_fraction(axis.to_command(0.9)))
        self.assertAlmostEqual(0.0, axis.to_fraction(axis.to_command(-0.2)))
        self.assertAlmostEqual(0.6, axis.max_fraction)
        # inside the band the round trip is exact up to command
        # quantization of one command unit = 1/scale in fractions
        for fraction in (0.0, 0.1, 0.35, 0.6):
            achieved = axis.to_fraction(axis.to_command(fraction))
            self.assertAlmostEqual(fraction, achieved, delta=1 / axis.scale)

    def test_axis_command_is_int(self):
        """
        the command reaches the camera as the string "x,y" - a float
        like "1656.0" is silently dropped by the camera, so every
        command must be an int even when the calibration was loaded
        with float values from yaml
        """
        float_axis = Axis(scale=2548.0, offset=213.0, cmd_max=1656.0)
        for fraction in (0.0, 0.5, 1.0):
            command = float_axis.to_command(fraction)
            self.assertIsInstance(command, int, msg=f"fraction {fraction}")

    def test_eos1000d_calibration(self):
        """
        the shipped Canon EOS 1000D calibration must reproduce the
        two facts measured on the ruler scene: the x axis reaches
        the full view width while the y axis saturates before the
        bottom - the camera cannot frame the lowest stripe of the
        view, so the achieved position must say so instead of the
        wish
        """
        geometry = self.eos1000d.geometry
        # x: the rightmost window position touches the right border
        x_reach = geometry.x_axis.max_fraction + geometry.window_width
        self.assertAlmostEqual(1.0, x_reach, delta=0.01)
        # y: the lowest window position leaves a visible stripe
        y_reach = geometry.y_axis.max_fraction + geometry.window_height
        self.assertLess(y_reach, 0.95)
        # a wish below the reachable band lands at the y clamp
        command = geometry.to_command(0.4, 0.69)
        x0, y0 = geometry.achieved(*command)
        self.assertAlmostEqual(0.4, x0, delta=0.01)
        self.assertAlmostEqual(geometry.y_axis.max_fraction, y0)

    def test_rotation_does_not_move_the_command(self):
        """
        issue 41 acceptance: the same scene point clicked on any
        rotated view must yield the same camera command - the
        magnifying frame is anchored to the scene, not the screen
        """
        geometry = self.eos1000d.geometry
        scene_point = (0.3, 0.4)
        reference = geometry.to_command(*scene_point)
        for degrees in (0, 90, 180, 270):
            rotation = Rotation(degrees)
            # what the user clicks on the rotated display ...
            display_point = rotation.to_display(*scene_point)
            # ... maps back to the scene before commanding
            sx, sy = rotation.to_sensor(*display_point)
            command = geometry.to_command(sx, sy)
            self.assertEqual(reference, command, msg=f"rotation {degrees}")

    def test_grid(self):
        """
        Grid converts between unit square fractions and the pixel
        raster of a frame - to_pixels and to_fractions must invert
        each other on pixel exact fractions
        """
        grid = Grid(3888, 2592)
        quarter_point = (0.25, 0.5)
        pixels = grid.to_pixels(*quarter_point)
        self.assertEqual((3888 // 4, 2592 // 2), pixels)
        fractions = grid.to_fractions(*pixels)
        self.assertAlmostEqual(quarter_point[0], fractions[0])
        self.assertAlmostEqual(quarter_point[1], fractions[1])
