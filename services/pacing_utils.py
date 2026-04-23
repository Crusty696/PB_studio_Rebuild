import math
from scipy import stats

class WilsonLowerBound:
    """
    Helper class to calculate the Wilson score interval lower bound.
    This is used to estimate the confidence of a Bernoulli process.
    """

    @staticmethod
    def calculate(ups: int, total: int, confidence: float = 0.95) -> float:
        """
        Calculates the lower bound of the Wilson score interval.
        
        Formula:
        L = (1 / (1 + z^2/n)) * (p_hat + z^2/(2n) - z * sqrt(p_hat*(1-p_hat)/n + z^2/(4n^2)))
        
        Args:
            ups (int): Number of successes (positive outcomes).
            total (int): Total number of samples.
            confidence (float): Confidence level (default 0.95).
            
        Returns:
            float: The lower bound of the Wilson score interval (between 0.0 and 1.0).
            
        Raises:
            ValueError: If ups > total or total < 0.
        """
        if total == 0:
            return 0.0
        
        if total < 0:
            raise ValueError("Total must be non-negative.")
            
        if ups > total:
            raise ValueError(f"Number of successes (ups={ups}) cannot exceed total samples (total={total}).")
        
        if ups < 0:
            raise ValueError("Ups must be non-negative.")

        # Z-score for the given confidence level
        # For 95% confidence, alpha = 0.05, tail = 0.025, z approx 1.96
        z = stats.norm.ppf(1 - (1 - confidence) / 2)
        
        n = float(total)
        p_hat = float(ups) / n
        
        # Wilson score interval components
        z2 = z * z
        denom = 1 + z2 / n
        adj_p = p_hat + z2 / (2 * n)
        err = z * math.sqrt((p_hat * (1 - p_hat) / n) + (z2 / (4 * n * n)))
        
        lower_bound = (adj_p - err) / denom
        
        # Ensure result is within [0.0, 1.0] due to floating point precision
        return max(0.0, min(1.0, float(lower_bound)))

def wilson_lower_bound(ups: int, total: int, confidence: float = 0.95) -> float:
    """Convenience wrapper for WilsonLowerBound.calculate."""
    return WilsonLowerBound.calculate(ups, total, confidence)
