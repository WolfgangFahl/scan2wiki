"""
Created on 2026-08-23

geometry - the standard grid for cam2web coordinate handling

The canonical space is the unrotated sensor unit square with
fractions 0..1 on both axes. Display coordinates only exist at the
edges - mouse input and overlay drawing - and are related to the
canonical space by a quarter turn Rotation. Keeping all state on the
standard grid makes rotation a pure view transform.
see https://github.com/WolfgangFahl/scan2wiki/issues/38
and https://github.com/WolfgangFahl/scan2wiki/issues/39

@author: wf
"""

from dataclasses import dataclass
from typing import Tuple


@dataclass
class Rotation:
    """
    clockwise display rotation in whole quarter turns - maps points
    and boxes between the sensor unit square and the rotated display
    unit square
    """

    degrees: int = 0

    def turn(self, delta: int) -> int:
        """
        step the rotation by the given signed degrees

        Args:
            delta (int): degrees to add, positive turns clockwise

        Returns:
            int: the new rotation in degrees 0..359
        """
        self.degrees = (self.degrees + delta) % 360
        return self.degrees

    @property
    def quarter(self) -> int:
        """
        the rotation as a count of clockwise quarter turns 0..3
        """
        quarter = (self.degrees % 360) // 90
        return quarter

    @property
    def swaps_axes(self) -> bool:
        """
        whether the rotation swaps the horizontal and vertical axes
        """
        swaps = self.quarter % 2 == 1
        return swaps

    def to_display(self, sx: float, sy: float) -> Tuple[float, float]:
        """
        map a sensor point to the rotated display

        Args:
            sx (float): horizontal sensor fraction
            sy (float): vertical sensor fraction

        Returns:
            Tuple[float, float]: (dx, dy) display fractions
        """
        if self.quarter == 1:
            point = (1.0 - sy, sx)
        elif self.quarter == 2:
            point = (1.0 - sx, 1.0 - sy)
        elif self.quarter == 3:
            point = (sy, 1.0 - sx)
        else:
            point = (sx, sy)
        return point

    def to_sensor(self, dx: float, dy: float) -> Tuple[float, float]:
        """
        map a display point back to the sensor

        Args:
            dx (float): horizontal display fraction
            dy (float): vertical display fraction

        Returns:
            Tuple[float, float]: (sx, sy) sensor fractions
        """
        if self.quarter == 1:
            point = (dy, 1.0 - dx)
        elif self.quarter == 2:
            point = (1.0 - dx, 1.0 - dy)
        elif self.quarter == 3:
            point = (1.0 - dy, dx)
        else:
            point = (dx, dy)
        return point

    def size_to_display(self, width: float, height: float) -> Tuple[float, float]:
        """
        map a sensor size to the rotated display

        Args:
            width (float): horizontal sensor extent
            height (float): vertical sensor extent

        Returns:
            Tuple[float, float]: (width, height) in display orientation
        """
        size = (height, width) if self.swaps_axes else (width, height)
        return size

    def box_to_display(
        self, x0: float, y0: float, width: float, height: float
    ) -> Tuple[float, float, float, float]:
        """
        map an axis aligned sensor box to the rotated display

        Args:
            x0 (float): left sensor fraction
            y0 (float): top sensor fraction
            width (float): horizontal sensor extent
            height (float): vertical sensor extent

        Returns:
            Tuple[float, float, float, float]: (x0, y0, width, height)
                display fractions
        """
        if self.quarter == 1:
            box = (1.0 - y0 - height, x0, height, width)
        elif self.quarter == 2:
            box = (1.0 - x0 - width, 1.0 - y0 - height, width, height)
        elif self.quarter == 3:
            box = (y0, 1.0 - x0 - width, height, width)
        else:
            box = (x0, y0, width, height)
        return box


@dataclass
class Window:
    """
    an axis aligned window on the standard grid given by its center
    and size as sensor fractions - the magnifying frame of issue 39
    """

    cx: float = 0.5
    cy: float = 0.5
    width: float = 0.1
    height: float = 0.1

    def move_to(self, cx: float, cy: float):
        """
        move the window center, clamped to the grid

        Args:
            cx (float): horizontal center fraction
            cy (float): vertical center fraction
        """
        self.cx = min(max(cx, 0.0), 1.0)
        self.cy = min(max(cy, 0.0), 1.0)

    def resize(self, width: float, height: float):
        """
        set the window size

        Args:
            width (float): horizontal extent as fraction
            height (float): vertical extent as fraction
        """
        self.width = width
        self.height = height

    def top_left(self) -> Tuple[float, float]:
        """
        the window top left corner clamped so that the window lies
        inside the grid

        Returns:
            Tuple[float, float]: (x0, y0) fractions
        """
        x0 = min(max(self.cx - self.width / 2, 0.0), 1.0 - self.width)
        y0 = min(max(self.cy - self.height / 2, 0.0), 1.0 - self.height)
        return x0, y0

    def box(self) -> Tuple[float, float, float, float]:
        """
        the clamped window as a box

        Returns:
            Tuple[float, float, float, float]: (x0, y0, width, height)
                fractions
        """
        x0, y0 = self.top_left()
        box = (x0, y0, self.width, self.height)
        return box

    def contains(self, fx: float, fy: float) -> bool:
        """
        whether the given point lies inside the clamped window

        Args:
            fx (float): horizontal fraction
            fy (float): vertical fraction

        Returns:
            bool: True if the point is inside
        """
        x0, y0 = self.top_left()
        inside = x0 <= fx <= x0 + self.width and y0 <= fy <= y0 + self.height
        return inside


@dataclass
class Grid:
    """
    a pixel grid of the given size - converts standard grid fractions
    to pixel coordinates
    """

    width: int
    height: int

    def to_pixels(self, fx: float, fy: float) -> Tuple[int, int]:
        """
        convert the given fractions to pixel coordinates

        Args:
            fx (float): horizontal fraction
            fy (float): vertical fraction

        Returns:
            Tuple[int, int]: (x, y) pixel coordinates
        """
        pixels = (int(fx * self.width), int(fy * self.height))
        return pixels

    def to_fractions(self, x: float, y: float) -> Tuple[float, float]:
        """
        convert the given pixel coordinates to fractions

        Args:
            x (float): horizontal pixel coordinate
            y (float): vertical pixel coordinate

        Returns:
            Tuple[float, float]: (fx, fy) fractions
        """
        fractions = (x / self.width, y / self.height)
        return fractions
