"""Cryo/Slushie recommendation engine subclass."""

from .base import BaseEngine

class CryoEngine(BaseEngine):
    """Engine specific to Cryo-Slushie Lab."""
    
    drink_type: str = 'SLUSHIE'
    finishers = ['Chill', 'Glacier', 'Frost', 'Slush', 'Ice', 'Cryo', 'Zero']
