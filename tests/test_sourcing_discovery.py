from email.message import EmailMessage
import mailbox
from pathlib import Path

from achat_immo.sourcing_discovery import (
    extract_jinka_ad_urls,
    extract_jinka_alert_ids,
    extract_jinka_alert_ids_from_message,
    extract_jinka_notification_count_from_message,
    extract_jinka_urls_from_message,
    read_jinka_alert_archive,
    read_source_archive,
)


JINKA_ID = "53fb9eba-25dc-462b-9443-5286e9f15b9d"
CANONICAL_URL = f"https://www.jinka.fr/ad/{JINKA_ID}"
ALERT_ID = "9aa8e8eab78a4e21034e334d90719be0"


def test_extract_jinka_ad_urls_canonise_et_dedoublonne() -> None:
    text = f"""
    <a href="https://www.jinka.fr/ad/{JINKA_ID}?alert_id=abc&amp;utm_source=mail">Annonce</a>
    https://jinka.fr/ad/{JINKA_ID}?from=jinka_share
    https://www.jinka.fr/legal
    """

    assert extract_jinka_ad_urls(text) == [CANONICAL_URL]


def test_extract_jinka_ad_urls_suit_une_redirection_encodee() -> None:
    wrapped = (
        "https://tracking.example/click?url=https%3A%2F%2Fwww.jinka.fr%2Fad%2F"
        f"{JINKA_ID}%3Futm_source%3Demail"
    )

    assert extract_jinka_ad_urls(wrapped) == [CANONICAL_URL]


def test_extract_jinka_urls_from_message_lit_html_et_texte() -> None:
    message = EmailMessage()
    message.set_content(f"Nouvelle annonce : https://jinka.fr/ad/{JINKA_ID}?alert_id=abc")
    message.add_alternative(
        f'<a href="https://www.jinka.fr/ad/{JINKA_ID}?utm_medium=email">Voir</a>',
        subtype="html",
    )

    assert extract_jinka_urls_from_message(message) == [CANONICAL_URL]


def test_extract_jinka_alert_ids_depuis_url_directe() -> None:
    text = f"https://www.jinka.fr/app-redirect?path=%2Falert%2F%3Falert_id%3D{ALERT_ID}"

    assert extract_jinka_alert_ids(text) == [ALERT_ID]


def test_extract_jinka_alert_ids_resout_uniquement_le_bouton_application() -> None:
    message = EmailMessage()
    message.set_content(
        "\n".join(
            [
                "Bonjour,",
                "4 nouvelles annonces ont ete recues.",
                "[Voir dans l'application Jinka](https://u6622232.ct.sendgrid.net/ls/click?view=1)",
                "[Desactiver l'alerte](https://u6622232.ct.sendgrid.net/ls/click?disable=1)",
            ]
        )
    )
    called_urls: list[str] = []

    def resolver(url: str) -> str:
        called_urls.append(url)
        return f"https://www.jinka.fr/app-redirect?path=%2Falert%2F%3Falert_id%3D{ALERT_ID}"

    assert extract_jinka_alert_ids_from_message(message, resolve_tracked_links=True, resolver=resolver) == [
        ALERT_ID
    ]
    assert called_urls == ["https://u6622232.ct.sendgrid.net/ls/click?view=1"]
    assert extract_jinka_notification_count_from_message(message) == 4


def test_read_source_archive_accepte_csv_eml_et_mbox(tmp_path: Path) -> None:
    csv_path = tmp_path / "annonces.csv"
    csv_path.write_text(
        f"titre;url\nBien;https://jinka.fr/ad/{JINKA_ID}?alert_id=csv\n",
        encoding="utf-8",
    )

    eml_path = tmp_path / "alerte.eml"
    eml = EmailMessage()
    eml.set_content(f"https://www.jinka.fr/ad/{JINKA_ID}?utm_source=eml")
    eml_path.write_bytes(eml.as_bytes())

    mbox_path = tmp_path / "historique.mbox"
    archive = mailbox.mbox(mbox_path)
    try:
        mbox_message = EmailMessage()
        mbox_message.set_content(f"https://jinka.fr/ad/{JINKA_ID}?from=mbox")
        archive.add(mbox_message)
        archive.flush()
    finally:
        archive.close()

    assert read_source_archive(csv_path) == [CANONICAL_URL]
    assert read_source_archive(eml_path) == [CANONICAL_URL]
    assert read_source_archive(mbox_path) == [CANONICAL_URL]
    assert read_source_archive(tmp_path) == [CANONICAL_URL]


def test_read_jinka_alert_archive_accepte_exports_directs(tmp_path: Path) -> None:
    eml_path = tmp_path / "alerte.eml"
    eml = EmailMessage()
    eml.set_content(f"https://www.jinka.fr/alerts?alert_id={ALERT_ID}")
    eml_path.write_bytes(eml.as_bytes())

    csv_path = tmp_path / "alertes.csv"
    csv_path.write_text(f"url\nhttps://www.jinka.fr/alerts?alert_id={ALERT_ID}\n", encoding="utf-8")

    assert read_jinka_alert_archive(eml_path) == [ALERT_ID]
    assert read_jinka_alert_archive(csv_path) == [ALERT_ID]
