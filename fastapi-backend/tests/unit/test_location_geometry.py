"""Unit tests for Location model geometry functionality."""
import pytest
from shapely.geometry import Point
from geoalchemy2.shape import to_shape, from_shape

from app.models.location import Location


def test_location_set_coordinates():
    """Test setting coordinates updates both lat/lon and geometry fields."""
    location = Location(
        name="Test Location",
        address1="123 Main St",
        city="Test City",
        state="CA",
        country="USA",
        zipcode="12345",
        location_type="user"
    )
    
    # Set coordinates
    latitude = 37.7749
    longitude = -122.4194
    location.set_coordinates(latitude, longitude)
    
    # Verify latitude and longitude fields are set
    assert location.latitude == latitude
    assert location.longitude == longitude
    
    # Verify geometry field is set
    assert location.coordinates is not None
    point = to_shape(location.coordinates)
    assert isinstance(point, Point)
    assert point.y == pytest.approx(latitude)
    assert point.x == pytest.approx(longitude)


def test_location_lat_property():
    """Test lat property returns latitude from geometry or latitude field."""
    location = Location(
        name="Test Location",
        address1="123 Main St",
        city="Test City",
        state="CA",
        country="USA",
        zipcode="12345",
        location_type="user"
    )
    
    # Test with geometry set
    latitude = 37.7749
    longitude = -122.4194
    location.set_coordinates(latitude, longitude)
    assert location.lat == pytest.approx(latitude)
    
    # Test with only latitude field set (no geometry)
    location2 = Location(
        name="Test Location 2",
        address1="456 Oak Ave",
        city="Test City",
        state="CA",
        country="USA",
        zipcode="12345",
        location_type="user",
        latitude=40.7128,
        longitude=None,
        coordinates=None
    )
    assert location2.lat == 40.7128


def test_location_lon_property():
    """Test lon property returns longitude from geometry or longitude field."""
    location = Location(
        name="Test Location",
        address1="123 Main St",
        city="Test City",
        state="CA",
        country="USA",
        zipcode="12345",
        location_type="user"
    )
    
    # Test with geometry set
    latitude = 37.7749
    longitude = -122.4194
    location.set_coordinates(latitude, longitude)
    assert location.lon == pytest.approx(longitude)
    
    # Test with only longitude field set (no geometry)
    location2 = Location(
        name="Test Location 2",
        address1="456 Oak Ave",
        city="Test City",
        state="CA",
        country="USA",
        zipcode="12345",
        location_type="user",
        latitude=None,
        longitude=-74.0060,
        coordinates=None
    )
    assert location2.lon == -74.0060


def test_location_get_coordinates_tuple():
    """Test get_coordinates_tuple returns (lat, lon) tuple."""
    location = Location(
        name="Test Location",
        address1="123 Main St",
        city="Test City",
        state="CA",
        country="USA",
        zipcode="12345",
        location_type="user"
    )
    
    # Test with geometry set
    latitude = 37.7749
    longitude = -122.4194
    location.set_coordinates(latitude, longitude)
    coords = location.get_coordinates_tuple()
    assert coords is not None
    assert coords[0] == pytest.approx(latitude)
    assert coords[1] == pytest.approx(longitude)
    
    # Test with lat/lon fields but no geometry
    location2 = Location(
        name="Test Location 2",
        address1="456 Oak Ave",
        city="Test City",
        state="CA",
        country="USA",
        zipcode="12345",
        location_type="user",
        latitude=40.7128,
        longitude=-74.0060,
        coordinates=None
    )
    coords2 = location2.get_coordinates_tuple()
    assert coords2 is not None
    assert coords2[0] == 40.7128
    assert coords2[1] == -74.0060
    
    # Test with no coordinates
    location3 = Location(
        name="Test Location 3",
        address1="789 Pine St",
        city="Test City",
        state="CA",
        country="USA",
        zipcode="12345",
        location_type="user",
        latitude=None,
        longitude=None,
        coordinates=None
    )
    coords3 = location3.get_coordinates_tuple()
    assert coords3 is None


def test_location_repr_with_coordinates():
    """Test __repr__ includes coordinates when set."""
    location = Location(
        name="Test Location",
        address1="123 Main St",
        city="Test City",
        state="CA",
        country="USA",
        zipcode="12345",
        location_type="user"
    )
    location.id = 1
    location.set_coordinates(37.7749, -122.4194)
    
    repr_str = repr(location)
    assert "Location" in repr_str
    assert "id=1" in repr_str
    assert "name=Test Location" in repr_str
    assert "lat=" in repr_str
    assert "lon=" in repr_str
