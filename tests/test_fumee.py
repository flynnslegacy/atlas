def test_le_paquet_core_est_importable():
    import atlas_core

    assert atlas_core.__version__ == "0.1.0"
