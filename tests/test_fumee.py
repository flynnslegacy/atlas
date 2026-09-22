def test_le_paquet_core_est_importable():
    import helios_core

    assert helios_core.__version__ == "0.1.0"
