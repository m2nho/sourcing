def test_package_imports():
    import sourcing

    assert sourcing is not None


def test_dependencies_available():
    import phonenumbers
    import selectolax.parser

    assert phonenumbers.parse("+6281234567890", None) is not None
    assert selectolax.parser.HTMLParser("<h1>x</h1>").css_first("h1").text() == "x"
