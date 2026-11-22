from ai.recommendations.scoring import training_fingerprint, training_identity


def test_fingerprint_is_canonical_and_excludes_generated_ids():
    rows=[('UG','career','A',1.234),('GR','career','A',3)]
    assert training_fingerprint(rows)==training_fingerprint(list(reversed(rows)))
    assert training_fingerprint(rows)==training_fingerprint([('UG','career','A',1.23400001),rows[1]])
    for changed in [('UG','other','A',1.234),('UG','career','B',1.234),('GR','career','A',1.234),('UG','career','A',1.235)]:
        assert training_fingerprint(rows)!=training_fingerprint([changed,rows[1]])
    assert training_identity(training_fingerprint(rows)).endswith(training_fingerprint(rows))


def test_training_version_changes_identity_without_changing_matrix(monkeypatch):
    from ai.recommendations import scoring
    fingerprint=training_fingerprint([('UG','career','A',1)])
    old=training_identity(fingerprint)
    monkeypatch.setattr(scoring,'ALS_TRAINING_VERSION','new-settings')
    assert training_identity(fingerprint)!=old
