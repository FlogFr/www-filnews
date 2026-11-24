from django.test import SimpleTestCase

from filnews.analysis.text import extract_tags
from filnews.elections import CANDIDATES
from filnews.vocabulary import lookup


class CandidatesTests(SimpleTestCase):
    def test_candidate_tags_are_personalities_of_the_vocabulary(self):
        for candidate in CANDIDATES:
            for name in candidate.tag_names:
                with self.subTest(candidate=candidate.name, tag=name):
                    entry = lookup(name)
                    self.assertIsNotNone(entry)
                    self.assertEqual(entry.kind, "personnalite")

    def test_candidate_slugs_are_unique(self):
        slugs = [candidate.slug for candidate in CANDIDATES]
        self.assertEqual(len(slugs), len(set(slugs)))

    def test_new_candidate_gets_a_tag(self):
        self.assertIn(
            "Teddy Riner",
            extract_tags(
                title="Teddy Riner annonce sa candidature à l'élection "
                "présidentielle 2027"
            ),
        )
