from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

User = get_user_model()


class RegistrationTests(TestCase):
    data = {"username": "newuser", "email": "New@Example.com", "password1": "S3cure-pass-xyz", "password2": "S3cure-pass-xyz"}

    def test_register_creates_user_logs_in_and_lowercases_email(self):
        response = self.client.post(reverse("accounts:register"), self.data, follow=True)
        user = User.objects.get(username="newuser")
        self.assertEqual(user.email, "new@example.com")
        self.assertRedirects(response, reverse("analytics:overview"))
        self.assertContains(response, "Welcome, newuser")

    def test_duplicate_email_is_rejected_case_insensitively(self):
        User.objects.create_user("old", "new@example.com", "pass12345!")
        response = self.client.post(reverse("accounts:register"), self.data)
        self.assertContains(response, "already exists")
        self.assertEqual(User.objects.count(), 1)

    def test_weak_password_is_rejected(self):
        bad = {**self.data, "password1": "12345678", "password2": "12345678"}
        response = self.client.post(reverse("accounts:register"), bad)
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(response.status_code, 200)

    @override_settings(ALLOW_REGISTRATION=False)
    def test_registration_can_be_closed(self):
        self.assertEqual(self.client.get(reverse("accounts:register")).status_code, 404)
        self.client.post(reverse("accounts:register"), self.data)
        self.assertEqual(User.objects.count(), 0)


class LoginLogoutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ana", "ana@example.com", "pass12345!")

    def test_login_page_is_public(self):
        self.assertEqual(self.client.get(reverse("accounts:login")).status_code, 200)

    def test_login_success_and_redirect_to_next(self):
        response = self.client.post(
            reverse("accounts:login") + "?next=" + reverse("analytics:upload"),
            {"username": "ana", "password": "pass12345!"},
        )
        self.assertRedirects(response, reverse("analytics:upload"))

    def test_login_failure_shows_error(self):
        response = self.client.post(reverse("accounts:login"), {"username": "ana", "password": "wrong"})
        self.assertContains(response, "Please enter a correct")

    def test_external_next_url_is_not_followed(self):
        response = self.client.post(
            reverse("accounts:login") + "?next=https://evil.example/",
            {"username": "ana", "password": "pass12345!"},
        )
        self.assertRedirects(response, reverse("analytics:overview"))

    def test_logout_requires_post_and_ends_session(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        self.client.post(reverse("accounts:logout"))
        self.assertEqual(self.client.get(reverse("analytics:overview")).status_code, 302)

    def test_csrf_is_enforced_on_login(self):
        from django.test import Client

        strict = Client(enforce_csrf_checks=True)
        response = strict.post(reverse("accounts:login"), {"username": "ana", "password": "pass12345!"})
        self.assertEqual(response.status_code, 403)

    def test_admin_login_page_still_reachable(self):
        self.assertEqual(self.client.get("/admin/login/").status_code, 200)


class PasswordTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ana", "ana@example.com", "pass12345!")

    def test_change_password(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("accounts:password_change"),
            {"old_password": "pass12345!", "new_password1": "An0ther-strong-pw", "new_password2": "An0ther-strong-pw"},
        )
        self.assertRedirects(response, reverse("accounts:password_change_done"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("An0ther-strong-pw"))

    def test_reset_flow_sends_email_with_working_link(self):
        response = self.client.post(reverse("accounts:password_reset"), {"email": "ana@example.com"})
        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        link = next(line for line in mail.outbox[0].body.splitlines() if "/reset/" in line)
        page = self.client.get(link.split("testserver")[1], follow=True)
        self.assertContains(page, "Choose a new password")
        post_url = page.redirect_chain[-1][0]
        done = self.client.post(post_url, {"new_password1": "Br4nd-new-pass", "new_password2": "Br4nd-new-pass"})
        self.assertRedirects(done, reverse("accounts:password_reset_complete"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Br4nd-new-pass"))

    def test_reset_for_unknown_email_does_not_reveal_it(self):
        response = self.client.post(reverse("accounts:password_reset"), {"email": "nobody@example.com"})
        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_settings_page_requires_login_and_shows_account(self):
        self.assertEqual(self.client.get(reverse("accounts:settings")).status_code, 302)
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse("accounts:settings")), "ana@example.com")
