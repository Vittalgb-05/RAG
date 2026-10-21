# ------------------------------------------------------------------
# Unit Tests for VectorIndex
# Verifies distance math, guard clauses, ranking, and edge cases
# ------------------------------------------------------------------

import pytest
from retrieval.vector_index import VectorIndex


def test_vector_index_initialization():
    """Verify initialization options and metric whitelist."""
    idx = VectorIndex(distance_metric="cosine")
    assert idx._distance_metric == "cosine"
    assert idx._vector_dim is None

    # Invalid metric raises ValueError
    with pytest.raises(ValueError, match="distance_metric must be 'cosine' or 'euclidean'"):
        VectorIndex(distance_metric="manhattan")


def test_cosine_distance_math():
    """Test exact cosine distance for identical, orthogonal, and opposite vectors."""
    idx = VectorIndex(distance_metric="cosine")

    # Identical vectors -> cosine similarity = 1.0 -> distance = 0.0
    dist_same = idx._cosine_distance([1.0, 0.0, 0.0], [1.0, 0.0, 0.0])
    assert pytest.approx(dist_same, abs=1e-5) == 0.0

    # Orthogonal vectors -> cosine similarity = 0.0 -> distance = 1.0
    dist_ortho = idx._cosine_distance([1.0, 0.0, 0.0], [0.0, 1.0, 0.0])
    assert pytest.approx(dist_ortho, abs=1e-5) == 1.0

    # Opposite vectors -> cosine similarity = -1.0 -> distance = 2.0
    dist_opp = idx._cosine_distance([1.0, 0.0, 0.0], [-1.0, 0.0, 0.0])
    assert pytest.approx(dist_opp, abs=1e-5) == 2.0


def test_euclidean_distance_math():
    """Test Euclidean distance calculation."""
    idx = VectorIndex(distance_metric="euclidean")

    # [0, 0] to [3, 4] -> distance = 5.0
    dist = idx._euclidean_distance([0.0, 0.0], [3.0, 4.0])
    assert pytest.approx(dist, abs=1e-5) == 5.0


def test_add_vector_guards():
    """Test input validation and dimension lock-in guards."""
    idx = VectorIndex()

    # Non-list vector raises TypeError
    with pytest.raises(TypeError, match="Vector must be a list of numbers"):
        idx.add_vector("not_a_list", {"content": "test"})  # type: ignore

    # Non-numeric elements raise TypeError
    with pytest.raises(TypeError, match="Vector must be a list of numbers"):
        idx.add_vector([1.0, "two", 3.0], {"content": "test"})  # type: ignore

    # Non-dict document raises TypeError
    with pytest.raises(TypeError, match="Document must be a dictionary"):
        idx.add_vector([1.0, 2.0, 3.0], "not_a_dict")  # type: ignore

    # Missing 'content' key raises ValueError
    with pytest.raises(ValueError, match="Document dictionary must contain a 'content' key"):
        idx.add_vector([1.0, 2.0, 3.0], {"id": 1})

    # Successful first addition locks in dimension
    idx.add_vector([1.0, 2.0, 3.0], {"content": "first"})
    assert idx._vector_dim == 3
    assert len(idx) == 1

    # Dimension mismatch on subsequent addition raises ValueError
    with pytest.raises(ValueError, match="Inconsistent vector dimension"):
        idx.add_vector([1.0, 2.0], {"content": "short"})


def test_search_empty_store():
    """Searching an empty store should return empty list rather than error."""
    idx = VectorIndex()
    results = idx.search([1.0, 0.0, 0.0], k=5)
    assert results == []


def test_search_ranking():
    """Verify search returns results sorted by ascending distance."""
    idx = VectorIndex(distance_metric="euclidean")
    idx.add_vector([0.0, 0.0], {"content": "target"})
    idx.add_vector([1.0, 0.0], {"content": "close"})
    idx.add_vector([5.0, 0.0], {"content": "far"})

    results = idx.search([0.0, 0.0], k=3)
    assert len(results) == 3

    # Ranking: target (0.0) -> close (1.0) -> far (5.0)
    assert results[0][0]["content"] == "target"
    assert pytest.approx(results[0][1], abs=1e-5) == 0.0

    assert results[1][0]["content"] == "close"
    assert pytest.approx(results[1][1], abs=1e-5) == 1.0

    assert results[2][0]["content"] == "far"
    assert pytest.approx(results[2][1], abs=1e-5) == 5.0


def test_zero_magnitude_vector():
    """Verify zero-magnitude vectors do not trigger ZeroDivisionError."""
    idx = VectorIndex(distance_metric="cosine")
    dist = idx._cosine_distance([0.0, 0.0, 0.0], [1.0, 2.0, 3.0])
    assert dist == 1.0
