"""Invented quadrant/alpha fixtures for the PC sprite conversion path."""
import numpy as np
from xml1build import menu_raster as R


def test_raster_triangle_preserves_uv_orientation_and_clips_outside_pixels():
    pixels = np.zeros((4,4,4),np.uint8)
    pixels[:2,:2] = (255,0,0,255)
    pixels[:2,2:] = (0,255,0,255)
    pixels[2:,:2] = (0,0,255,255)
    pixels[2:,2:] = (255,255,255,255)
    canvas = np.zeros((8,8,4),np.float32)
    positions = np.array([[0,0,8],[8,0,8],[0,0,0]],float)
    R.triangle(canvas,positions,np.array([[0,0],[1,0],[0,1]],float),pixels)
    assert np.array_equal(canvas[1,1],(1,0,0,1))
    assert np.array_equal(canvas[1,5],(0,1,0,1))
    assert np.array_equal(canvas[5,1],(0,0,1,1))
    assert np.array_equal(canvas[6,6],(0,0,0,0))
    assert np.array_equal(R.sample(pixels,np.array([[1.25,-.25]]),True)[0],(0,0,1,1))


def test_raster_triangle_composites_straight_alpha_without_dark_fringes():
    canvas = np.full((8,8,4),(1,0,0,1),np.float32)
    pixels = np.full((4,4,4),(0,0,255,128),np.uint8)
    R.triangle(canvas,np.array([[0,0,8],[8,0,8],[0,0,0]],float),
               np.array([[0,0],[1,0],[0,1]],float),pixels)
    assert np.allclose(canvas[1,1],(127/255,0,128/255,1),atol=1e-6)
