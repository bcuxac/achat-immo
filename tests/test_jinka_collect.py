from achat_immo.jinka_collect import extract_jinka_ad_urls_from_payload, jinka_alert_url


def test_extract_jinka_ad_urls_from_payload_recupere_json_et_html() -> None:
    ad_id = "53fb9eba-25dc-462b-9443-5286e9f15b9d"
    payload = {
        "items": [
            {"url": f"https://www.jinka.fr/ad/{ad_id}?alert_id=abc"},
            {"html": f'<a href="https://jinka.fr/ad/{ad_id}?utm_source=network">Voir</a>'},
        ]
    }

    assert extract_jinka_ad_urls_from_payload(payload) == [f"https://www.jinka.fr/ad/{ad_id}"]


def test_jinka_alert_url_normalise_l_identifiant() -> None:
    alert_id = "9aa8e8eab78a4e21034e334d90719be0"

    assert jinka_alert_url(f" {alert_id} ") == f"https://www.jinka.fr/alerts?alert_id={alert_id}"
