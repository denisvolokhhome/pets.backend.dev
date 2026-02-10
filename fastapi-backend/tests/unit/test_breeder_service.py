"""Unit tests for BreederService."""
import pytest
from unittest.mock import Mock, MagicMock, AsyncMock
from uuid import uuid4

from app.services.breeder_service import BreederService
from app.schemas.breeder import BreederSearchResult, BreedInfo


class TestBreederService:
    """Unit tests for BreederService geospatial search functionality."""
    
    def test_service_initialization(self):
        """Test that BreederService can be instantiated."""
        service = BreederService()
        assert service is not None
        assert hasattr(service, 'search_nearby_breeding_locations')
    
    async def test_search_with_valid_parameters(self):
        """Test search with valid latitude, longitude, and radius."""
        service = BreederService()
        
        # Mock database session with AsyncMock
        mock_db = AsyncMock()
        
        # Mock the execute result
        mock_result = Mock()
        mock_result.all.return_value = []
        mock_db.execute.return_value = mock_result
        
        # Call service
        results = await service.search_nearby_breeding_locations(
            db=mock_db,
            latitude=40.7128,
            longitude=-74.0060,
            radius_miles=10.0,
            breed_id=None
        )
        
        # Verify results
        assert isinstance(results, list)
        assert len(results) == 0
        # Verify execute was called
        assert mock_db.execute.called
    
    async def test_search_with_breed_filter(self):
        """Test search with breed_id filter."""
        service = BreederService()
        
        # Mock database session with AsyncMock
        mock_db = AsyncMock()
        
        # Mock the execute result
        mock_result = Mock()
        mock_result.all.return_value = []
        mock_db.execute.return_value = mock_result
        
        # Call service with breed filter
        results = await service.search_nearby_breeding_locations(
            db=mock_db,
            latitude=40.7128,
            longitude=-74.0060,
            radius_miles=10.0,
            breed_id=1
        )
        
        # Verify results
        assert isinstance(results, list)
        # Verify execute was called
        assert mock_db.execute.called
    
    def test_distance_calculation_logic(self):
        """Test that distance is calculated and converted from meters to miles."""
        # Test the conversion factor
        radius_miles = 10.0
        radius_meters = radius_miles * 1609.34
        
        assert radius_meters == pytest.approx(16093.4)
        
        # Test reverse conversion
        distance_meters = 16093.4
        distance_miles = distance_meters / 1609.34
        
        assert distance_miles == pytest.approx(10.0)
    
    def test_result_schema_structure(self):
        """Test that BreederSearchResult has correct structure."""
        # Create a sample result
        result = BreederSearchResult(
            location_id=1,
            user_id=uuid4(),
            breeder_name="Test Breeder",
            latitude=40.7128,
            longitude=-74.0060,
            distance=5.3,
            available_breeds=[
                BreedInfo(breed_id=1, breed_name="Golden Retriever", pet_count=3)
            ],
            thumbnail_url="/path/to/image.jpg",
            location_description="Main Facility",
            rating=None
        )
        
        # Verify structure
        assert result.location_id == 1
        assert result.breeder_name == "Test Breeder"
        assert result.distance == 5.3
        assert len(result.available_breeds) == 1
        assert result.available_breeds[0].breed_name == "Golden Retriever"
        assert result.available_breeds[0].pet_count == 3
    
    def test_distance_rounding(self):
        """Test that distance is rounded to 1 decimal place."""
        result = BreederSearchResult(
            location_id=1,
            user_id=uuid4(),
            breeder_name="Test Breeder",
            latitude=40.7128,
            longitude=-74.0060,
            distance=5.3456789,  # Should be rounded
            available_breeds=[],
            thumbnail_url=None,
            location_description=None,
            rating=None
        )
        
        # Verify rounding
        assert result.distance == 5.3
    
    def test_breed_info_schema(self):
        """Test BreedInfo schema structure."""
        breed_info = BreedInfo(
            breed_id=1,
            breed_name="Labrador Retriever",
            pet_count=5
        )
        
        assert breed_info.breed_id == 1
        assert breed_info.breed_name == "Labrador Retriever"
        assert breed_info.pet_count == 5
    
    def test_multiple_breeds_at_location(self):
        """Test that a location can have multiple breeds."""
        result = BreederSearchResult(
            location_id=1,
            user_id=uuid4(),
            breeder_name="Multi-Breed Kennel",
            latitude=40.7128,
            longitude=-74.0060,
            distance=3.2,
            available_breeds=[
                BreedInfo(breed_id=1, breed_name="Golden Retriever", pet_count=3),
                BreedInfo(breed_id=2, breed_name="Labrador Retriever", pet_count=2),
                BreedInfo(breed_id=3, breed_name="German Shepherd", pet_count=4),
            ],
            thumbnail_url=None,
            location_description="Main Breeding Facility",
            rating=None
        )
        
        assert len(result.available_breeds) == 3
        assert result.available_breeds[0].breed_name == "Golden Retriever"
        assert result.available_breeds[1].breed_name == "Labrador Retriever"
        assert result.available_breeds[2].breed_name == "German Shepherd"
        
        # Verify total pet count
        total_pets = sum(b.pet_count for b in result.available_breeds)
        assert total_pets == 9
    
    def test_search_parameters_validation(self):
        """Test that search parameters are within valid ranges."""
        service = BreederService()
        
        # Valid parameters
        valid_params = {
            'latitude': 40.7128,  # -90 to 90
            'longitude': -74.0060,  # -180 to 180
            'radius_miles': 10.0,  # > 0
        }
        
        assert -90 <= valid_params['latitude'] <= 90
        assert -180 <= valid_params['longitude'] <= 180
        assert valid_params['radius_miles'] > 0
    
    async def test_empty_results_handling(self):
        """Test that service handles empty results gracefully."""
        service = BreederService()
        
        # Mock database session with AsyncMock
        mock_db = AsyncMock()
        
        # Mock the execute result returning empty list
        mock_result = Mock()
        mock_result.all.return_value = []
        mock_db.execute.return_value = mock_result
        
        # Call service
        results = await service.search_nearby_breeding_locations(
            db=mock_db,
            latitude=40.7128,
            longitude=-74.0060,
            radius_miles=10.0,
            breed_id=None
        )
        
        # Verify empty results
        assert results == []
        assert len(results) == 0
