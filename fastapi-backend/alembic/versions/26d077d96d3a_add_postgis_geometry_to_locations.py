"""add_postgis_geometry_to_locations

Revision ID: 26d077d96d3a
Revises: 4377215edbd1
Create Date: 2026-02-04 22:57:50.551186

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry


# revision identifiers, used by Alembic.
revision: str = '26d077d96d3a'
down_revision: Union[str, Sequence[str], None] = '4377215edbd1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to add PostGIS support and geometry column."""
    # Enable PostGIS extension
    op.execute('CREATE EXTENSION IF NOT EXISTS postgis')
    
    # Add latitude and longitude columns if they don't exist
    # These will be used to populate the geometry column
    # Only check columns when not in SQL generation mode
    try:
        connection = op.get_bind()
        # Check if we're in SQL generation mode (MockConnection)
        if hasattr(connection, 'execute'):
            inspector = sa.inspect(connection)
            columns = [col['name'] for col in inspector.get_columns('locations')]
            
            if 'latitude' not in columns:
                op.add_column(
                    'locations',
                    sa.Column('latitude', sa.Float(), nullable=True)
                )
            
            if 'longitude' not in columns:
                op.add_column(
                    'locations',
                    sa.Column('longitude', sa.Float(), nullable=True)
                )
    except Exception:
        # In SQL generation mode or if inspection fails, add columns unconditionally
        # The database will handle "IF NOT EXISTS" logic
        op.add_column(
            'locations',
            sa.Column('latitude', sa.Float(), nullable=True)
        )
        op.add_column(
            'locations',
            sa.Column('longitude', sa.Float(), nullable=True)
        )
    
    # Add geometry column to locations table
    # Using POINT geometry type with SRID 4326 (WGS84 coordinate system)
    # GeoAlchemy2 automatically creates a GIST spatial index
    op.add_column(
        'locations',
        sa.Column(
            'coordinates',
            Geometry(geometry_type='POINT', srid=4326),
            nullable=True
        )
    )


def downgrade() -> None:
    """Downgrade schema to remove PostGIS support."""
    # Drop spatial index
    op.execute('DROP INDEX IF EXISTS idx_locations_coordinates')
    
    # Drop geometry column
    op.drop_column('locations', 'coordinates')
    
    # Note: We don't drop latitude/longitude columns as they might be used elsewhere
    # Note: We don't drop PostGIS extension as other tables might use it
