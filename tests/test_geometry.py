"""
Created on 2026-08-23

tests for the standard grid geometry of cam2web
see https://github.com/WolfgangFahl/scan2wiki/issues/38
and https://github.com/WolfgangFahl/scan2wiki/issues/39

@author: wf
"""

from ngwidgets.basetest import Basetest

from scan.geometry import Calibration, Grid, Rotation, Window


class TestGeometry(Basetest):
    """
    test the standard grid coordinate handling
    """

    def test_rotation_round_trip(self):
        """
        test that to_display and to_sensor are inverse for all four
        quarter turns
        """
        points = [(0.0, 0.0), (0.25, 0.5), (1.0, 0.0), (0.7, 0.9)]
        for degrees in (0, 90, 180, 270):
            rotation = Rotation(degrees)
            for sx, sy in points:
                dx, dy = rotation.to_display(sx, sy)
                rx, ry = rotation.to_sensor(dx, dy)
                self.assertAlmostEqual(sx, rx, msg=f"rotation {degrees}")
                self.assertAlmostEqual(sy, ry, msg=f"rotation {degrees}")

    def test_to_sensor(self):
        """
        test the mapping of rotated display fractions back to sensor
        fractions - the eoszoomposition case of issue 39
        """
        point = (0.25, 0.5)
        expected = {
            0: (0.25, 0.5),
            90: (0.5, 0.75),
            180: (0.75, 0.5),
            270: (0.5, 0.25),
        }
        for degrees, sensor in expected.items():
            rotation = Rotation(degrees)
            fx, fy = rotation.to_sensor(*point)
            self.assertAlmostEqual(sensor[0], fx, msg=f"rotation {degrees}")
            self.assertAlmostEqual(sensor[1], fy, msg=f"rotation {degrees}")

    def test_turn(self):
        """
        test stepping the rotation in signed 90 degree increments
        """
        rotation = Rotation()
        self.assertEqual(90, rotation.turn(90))
        self.assertEqual(0, rotation.turn(-90))
        self.assertEqual(270, rotation.turn(-90))
        self.assertTrue(rotation.swaps_axes)
        self.assertFalse(Rotation(180).swaps_axes)

    def test_box_to_display(self):
        """
        test that a sensor box maps to the display box spanned by its
        mapped corners
        """
        box = (0.1, 0.2, 0.3, 0.4)
        for degrees in (0, 90, 180, 270):
            rotation = Rotation(degrees)
            x0, y0, width, height = rotation.box_to_display(*box)
            # the mapped corners of the sensor box span the display box
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
        test that the window box is clamped to the grid borders while
        the center is clamped to the unit square
        """
        window = Window(width=0.1, height=0.1)
        window.move_to(0.0, 0.0)
        x0, y0, width, height = window.box()
        self.assertEqual(0.0, x0)
        self.assertEqual(0.0, y0)
        self.assertAlmostEqual(0.1, width)
        self.assertAlmostEqual(0.1, height)
        window.move_to(1.5, -0.5)
        self.assertEqual(1.0, window.cx)
        self.assertEqual(0.0, window.cy)
        x0, y0, _, _ = window.box()
        self.assertAlmostEqual(0.9, x0)
        self.assertEqual(0.0, y0)
        self.assertTrue(window.contains(0.95, 0.05))
        self.assertFalse(window.contains(0.5, 0.5))

    def test_calibration(self):
        """
        test the issue 41 Dreisatz: command = center - measured offset
        """
        calibration = Calibration(dx=410, dy=143)
        self.assertEqual((1832, 1386), calibration.to_command(2242, 1529))
        self.assertEqual((0, 0), Calibration().to_command(0, 0))

    def test_grid(self):
        """
        test the fraction to pixel conversion
        """
        grid = Grid(3888, 2592)
        self.assertEqual((972, 1296), grid.to_pixels(0.25, 0.5))
        fx, fy = grid.to_fractions(972, 1296)
        self.assertAlmostEqual(0.25, fx)
        self.assertAlmostEqual(0.5, fy)
