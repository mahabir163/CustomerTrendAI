from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from analytics.context_processors import NAV_ITEMS


class SmokeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("ana", "ana@example.com", "pass12345!")
        self.client.force_login(self.user)

    def test_overview_renders_empty_state(self):
        response = self.client.get(reverse("analytics:overview"))
        self.assertContains(response, "No dataset yet")

    def test_every_sidebar_link_resolves_and_renders(self):
        for item in NAV_ITEMS:
            with self.subTest(item=item.label):
                response = self.client.get(reverse(item.url_name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, item.label)

    def test_sidebar_marks_active_page(self):
        self.assertContains(self.client.get(reverse("analytics:overview")), 'aria-current="page"')
