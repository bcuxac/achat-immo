import abc
import random
import numpy as np
from typing import Any

class Distribution(abc.ABC):
    """Classe de base pour une distribution de probabilité."""
    @abc.abstractmethod
    def sample(self, rng: random.Random | np.random.Generator) -> float:
        pass

class ConstantDist(Distribution):
    def __init__(self, value: float):
        self.value = value
        
    def sample(self, rng: Any) -> float:
        return self.value

class TriangularDist(Distribution):
    def __init__(self, low: float, mode: float, high: float):
        self.low = low
        self.mode = mode
        self.high = high
        
    def sample(self, rng: Any) -> float:
        if isinstance(rng, np.random.Generator):
            return rng.triangular(self.low, self.mode, self.high)
        # Fallback pour random.Random
        return rng.triangular(self.low, self.high, self.mode)

class TruncatedNormalDist(Distribution):
    def __init__(self, mean: float, std: float, low: float, high: float):
        self.mean = mean
        self.std = std
        self.low = low
        self.high = high
        
    def sample(self, rng: Any) -> float:
        # Rejection sampling simple pour rester dans les bornes
        while True:
            if isinstance(rng, np.random.Generator):
                val = rng.normal(self.mean, self.std)
            else:
                val = rng.gauss(self.mean, self.std)
                
            if self.low <= val <= self.high:
                return val

class BetaDist(Distribution):
    """Distribution Beta rescalée entre low et high."""
    def __init__(self, alpha: float, beta: float, low: float = 0.0, high: float = 1.0):
        self.alpha = alpha
        self.beta = beta
        self.low = low
        self.high = high
        
    def sample(self, rng: Any) -> float:
        if isinstance(rng, np.random.Generator):
            val = rng.beta(self.alpha, self.beta)
        else:
            val = rng.betavariate(self.alpha, self.beta)
        return self.low + val * (self.high - self.low)

class LogNormalDist(Distribution):
    def __init__(self, mean: float, sigma: float):
        self.mean = mean
        self.sigma = sigma
        
    def sample(self, rng: Any) -> float:
        if isinstance(rng, np.random.Generator):
            return rng.lognormal(self.mean, self.sigma)
        return rng.lognormvariate(self.mean, self.sigma)
