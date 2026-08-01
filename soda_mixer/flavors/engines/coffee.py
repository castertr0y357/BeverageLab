"""Coffee recommendation engine subclass."""

from .base import BaseEngine

class CoffeeEngine(BaseEngine):
    """Engine specific to Coffee Laboratory."""
    drink_type: str = 'COFFEE'
