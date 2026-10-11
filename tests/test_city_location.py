from pwrbnb.city_location import locate_city


def test_city_lookup_is_state_scoped_and_approximate():
    virginia = locate_city("Ashburn", "VA")
    georgia = locate_city("Ashburn", "Georgia")
    assert virginia and georgia
    assert virginia["latitude"] > 38
    assert georgia["latitude"] < 33
    assert virginia["longitude"] != georgia["longitude"]


def test_legacy_address_and_zip_lookup():
    assert locate_city(address="123 Example Road, Ashburn, VA 20147, USA") == locate_city("Ashburn", "VA")
    assert locate_city(address="Ashburn Virginia") == locate_city("Ashburn", "VA")


def test_unknown_and_marketing_regions_do_not_get_guessed_pins():
    assert locate_city("Ashburn", "") is None
    assert locate_city("Northern Virginia", "VA") is None
    assert locate_city(address="Location unconfirmed") is None
    assert locate_city("Invented campus", "TX") is None


def test_alaska_hawaii_and_washington():
    assert locate_city("Fairbanks", "AK")["latitude"] > 60
    assert locate_city("Urban Honolulu", "HI")["latitude"] < 25
    assert locate_city("Washington", "DC")
