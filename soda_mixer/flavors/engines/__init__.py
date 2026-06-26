"""Recommendation engines package."""

from .base import BaseEngine
from .soda import SodaEngine
from .coffee import CoffeeEngine
from .cryo import CryoEngine

_ENGINES = {
    'SODA': SodaEngine(),
    'COFFEE': CoffeeEngine(),
    'SLUSHIE': CryoEngine(),
}

def get_engine(drink_type: str) -> BaseEngine:
    """
    Factory function to retrieve the appropriate recommendation engine for the given drink type.
    """
    drink_type_upper = (drink_type or 'SODA').upper()
    if drink_type_upper == 'CRYO':
        drink_type_upper = 'SLUSHIE'
    return _ENGINES.get(drink_type_upper, _ENGINES['SODA'])

__all__ = ['BaseEngine', 'SodaEngine', 'CoffeeEngine', 'CryoEngine', 'get_engine']
