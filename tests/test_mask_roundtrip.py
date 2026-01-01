from scitrans.masking.engine import MaskingEngine


def test_mask_restore_roundtrip():
    eng = MaskingEngine()
    src = "This is $E=mc^2$ and a URL https://example.com and `code`."
    masked, registry, _ = eng.mask(src)
    assert masked != src
    restored, errors = eng.restore(masked, registry)
    assert errors == []
    assert restored == src
