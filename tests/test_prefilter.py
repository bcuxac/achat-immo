from achat_immo.sourcing_agents.prefilter import UrlPrefilterPolicy, prefilter_url


def test_prefilter_accepte_une_url_http_valide() -> None:
    decision = prefilter_url(" HTTPS://Jinka.fr/annonces/123/#tracking ")

    assert decision.accepted
    assert decision.normalized_url == "https://jinka.fr/annonces/123"
    assert decision.tags == ("accepted",)


def test_prefilter_rejette_les_urls_non_exploitables() -> None:
    assert not prefilter_url("").accepted
    assert "Schema non supporte" in prefilter_url("ftp://example.test/annonce").reason
    assert "Ressource statique" in prefilter_url("https://example.test/photo.jpg").reason
    assert "Chemin utilisateur" in prefilter_url("https://example.test/login").reason
    assert "Chemin technique" in prefilter_url("https://example.test/robots.txt").reason


def test_prefilter_restraint_les_domaines_si_une_liste_blanche_est_fournie() -> None:
    policy = UrlPrefilterPolicy(allowed_domains=("jinka.fr", "leboncoin.fr"))

    assert prefilter_url("https://www.leboncoin.fr/ad/ventes_immobilieres/123", policy).accepted

    rejected = prefilter_url("https://example.test/annonce/123", policy)
    assert not rejected.accepted
    assert rejected.tags == ("unsupported_domain",)
