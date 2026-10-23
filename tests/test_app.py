import io
import os
import re
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import pyotp

TOTP_SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"


class AppTestCase(unittest.TestCase):
    env = {}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "uploads"
        env = {
            "UPLOAD_FOLDER": str(self.root),
            "SECRET_KEY": "test-secret-key-that-is-long-enough-1234567890",
            "TOTP_SECRET": TOTP_SECRET,
            "BACKUP_CODES": "123456,backup-code-2",
            "LOG_LEVEL": "CRITICAL",
            **self.env,
        }
        patcher = mock.patch.dict(os.environ, env, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

        from securefilehub import create_app
        from securefilehub.config import load_settings

        self.app = create_app(load_settings())
        self.app.testing = True
        self.client = self.app.test_client()
        self.totp = pyotp.TOTP(TOTP_SECRET)

    # helpers

    def csrf(self):
        self.client.get("/login")
        with self.client.session_transaction() as sess:
            return sess["csrf"]

    def login(self, code=None):
        token = self.csrf()
        return self.client.post("/login", data={"code": code or self.totp.now(), "csrf_token": token})

    def put(self, name, content=b"data"):
        path = self.root / name
        path.write_bytes(content)
        return path


class AuthTests(AppTestCase):
    def test_pages_require_login(self):
        for url in ("/files", "/upload", "/files/x.txt", "/thumb/x.png"):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302, url)
            self.assertTrue(response.location.endswith("/login"))

    def test_login_with_totp(self):
        response = self.login()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get("/files").status_code, 200)

    def test_totp_code_cannot_be_replayed(self):
        code = self.totp.now()
        self.assertEqual(self.login(code).status_code, 302)
        self.client.post("/logout", data={"csrf_token": self.csrf()})
        self.assertEqual(self.login(code).status_code, 401)

    def test_backup_code_works_once(self):
        self.assertEqual(self.login("backup-code-2").status_code, 302)
        self.client.post("/logout", data={"csrf_token": self.csrf()})
        self.assertEqual(self.login("backup-code-2").status_code, 401)

    def test_login_requires_csrf(self):
        self.client.get("/login")
        response = self.client.post("/login", data={"code": self.totp.now()})
        self.assertEqual(response.status_code, 400)

    def test_rate_limit(self):
        for _ in range(5):
            self.assertEqual(self.login("000000").status_code, 401)
        self.assertEqual(self.login().status_code, 429)

    def test_forwarded_for_is_ignored_without_trusted_proxies(self):
        token = self.csrf()
        for i in range(5):
            self.client.post("/login", data={"code": "000000", "csrf_token": token},
                             headers={"X-Forwarded-For": f"10.0.0.{i}"})
        response = self.client.post("/login", data={"code": self.totp.now(), "csrf_token": token},
                                    headers={"X-Forwarded-For": "10.0.0.99"})
        self.assertEqual(response.status_code, 429)

    def test_logout_requires_post(self):
        self.login()
        self.assertEqual(self.client.get("/logout").status_code, 405)

    def test_language_switch_rejects_external_redirect(self):
        for target in ("https://evil.example", "//evil.example", "/\\evil.example"):
            response = self.client.get("/lang/ru", query_string={"next": target})
            self.assertEqual(response.location, "/")
        response = self.client.get("/lang/ru", query_string={"next": "/files"})
        self.assertEqual(response.location, "/files")

    def test_russian_translation(self):
        self.client.get("/lang/ru")
        self.assertIn("Войти".encode(), self.client.get("/login").data)

    def test_security_headers(self):
        response = self.client.get("/login")
        self.assertIn("script-src 'self'", response.headers["Content-Security-Policy"])
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        cookie = response.headers.get("Set-Cookie", "")
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)


class FileTests(AppTestCase):
    def setUp(self):
        super().setUp()
        self.login()
        with self.client.session_transaction() as sess:
            self.token = sess["csrf"]

    def upload(self, *files, headers=None):
        data = {"file": [(io.BytesIO(content), name) for name, content in files]}
        return self.client.post(
            "/upload", data=data, content_type="multipart/form-data",
            headers={"X-CSRF-Token": self.token, "X-Requested-With": "XMLHttpRequest", **(headers or {})},
        )

    def test_listing_hides_state_dir_and_dotfiles(self):
        self.put("visible.txt")
        self.put(".hidden")
        page = self.client.get("/files").data.decode()
        self.assertIn("visible.txt", page)
        self.assertNotIn(".hidden", page)
        self.assertNotIn(".securefilehub", page)

    def test_upload_and_duplicate_names(self):
        response = self.upload(("report.pdf", b"one"), ("report.pdf", b"two"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["saved"], ["report.pdf", "report (2).pdf"])
        self.assertEqual((self.root / "report (2).pdf").read_bytes(), b"two")
        self.assertEqual(list((self.root / ".securefilehub" / "incoming").iterdir()), [])

    def test_upload_requires_csrf(self):
        response = self.upload(("a.txt", b"x"), headers={"X-CSRF-Token": "wrong"})
        self.assertEqual(response.status_code, 400)
        self.assertFalse((self.root / "a.txt").exists())

    def test_upload_sanitizes_names(self):
        response = self.upload(("../../etc/passwd", b"x"), (".bashrc", b"y"), ('a<b>:c?.txt', b"z"),
                               ("Отчёт за май.docx", b"w"))
        self.assertEqual(response.json["saved"], ["passwd", "bashrc", "a_b__c_.txt", "Отчёт за май.docx"])

    def test_long_names_fit_filesystem_limit(self):
        response = self.upload(("я" * 300 + ".txt", b"x"))
        name = response.json["saved"][0]
        self.assertLessEqual(len(name.encode()), 255)
        self.assertTrue(name.endswith(".txt"))

    def test_download_and_traversal(self):
        self.put("hello.txt", b"hello")
        response = self.client.get("/files/hello.txt")
        self.assertEqual(response.data, b"hello")
        self.assertIn("attachment", response.headers["Content-Disposition"])
        self.assertIn("sandbox", response.headers["Content-Security-Policy"])
        for name in ("..%2Fsecret", ".securefilehub", "%2Fetc%2Fpasswd"):
            self.assertEqual(self.client.get(f"/files/{name}").status_code, 404, name)

    def test_symlinks_are_not_served(self):
        outside = Path(self.tmp.name) / "outside.txt"
        outside.write_text("secret")
        (self.root / "link.txt").symlink_to(outside)
        self.assertEqual(self.client.get("/files/link.txt").status_code, 404)
        self.assertNotIn("link.txt", self.client.get("/files").data.decode())

    def test_active_content_is_never_rendered(self):
        self.put("page.html", b"<script>alert(1)</script>")
        response = self.client.get("/files/page.html?inline=1")
        self.assertTrue(response.headers["Content-Type"].startswith("text/plain"))
        self.assertIn("sandbox", response.headers["Content-Security-Policy"])
        self.put("doc.docx")
        response = self.client.get("/files/doc.docx?inline=1")
        self.assertIn("attachment", response.headers["Content-Disposition"])

    def test_inline_preview(self):
        self.put("notes.md", b"# hi")
        response = self.client.get("/files/notes.md?inline=1")
        self.assertTrue(response.headers["Content-Type"].startswith("text/plain"))
        self.assertIn("inline", response.headers["Content-Disposition"])
        self.assertIn("sandbox", response.headers["Content-Security-Policy"])

    def test_range_requests(self):
        self.put("video.mp4", b"0123456789")
        response = self.client.get("/files/video.mp4", headers={"Range": "bytes=2-4"})
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.data, b"234")

    def test_delete(self):
        self.put("a.txt")
        self.put("b.txt")
        response = self.client.post("/delete", data={"name": ["a.txt", "b.txt", "missing", "../x"], "csrf_token": self.token},
                                    headers={"X-Requested-With": "XMLHttpRequest"})
        self.assertEqual(response.json["deleted"], ["a.txt", "b.txt"])
        self.assertEqual(response.json["failed"], ["missing", "../x"])
        self.assertFalse((self.root / "a.txt").exists())

    def test_delete_requires_csrf(self):
        self.put("a.txt")
        response = self.client.post("/delete", data={"name": "a.txt"})
        self.assertEqual(response.status_code, 400)
        self.assertTrue((self.root / "a.txt").exists())

    def test_zip_download(self):
        self.put("a.txt", b"aaa")
        self.put("b.bin", os.urandom(3 * 1024 * 1024))
        response = self.client.post("/download", data={"name": ["a.txt", "b.bin", "../nope"], "csrf_token": self.token})
        self.assertEqual(response.mimetype, "application/zip")
        archive = zipfile.ZipFile(io.BytesIO(response.data))
        self.assertEqual(sorted(archive.namelist()), ["a.txt", "b.bin"])
        self.assertIsNone(archive.testzip())
        self.assertEqual(archive.read("b.bin"), (self.root / "b.bin").read_bytes())

    def test_share_link(self):
        self.put("shared.txt", b"public")
        url = self.client.post("/share/shared.txt", headers={"X-CSRF-Token": self.token}).json["url"]
        path = url.split("localhost", 1)[1]
        anonymous = self.app.test_client()
        self.assertEqual(anonymous.get(path).data, b"public")
        # Replacing the file invalidates the link
        time.sleep(0.01)
        self.put("shared.txt", b"changed!")
        self.assertEqual(anonymous.get(path).status_code, 410)
        self.assertEqual(anonymous.get("/s/garbage").status_code, 410)

    def test_thumbnail(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is not installed")
        buffer = io.BytesIO()
        Image.new("RGB", (1200, 800), "red").save(buffer, "JPEG")
        self.put("photo.jpg", buffer.getvalue())
        page = self.client.get("/files").data.decode()
        url = re.search(r'src="(/thumb/photo\.jpg\?v=[0-9a-f]+)"', page).group(1)
        response = self.client.get(url)
        self.assertEqual(response.mimetype, "image/webp")
        self.assertIn("immutable", response.headers["Cache-Control"])
        with Image.open(io.BytesIO(response.data)) as thumb:
            self.assertLessEqual(max(thumb.size), 480)

    def test_broken_image_has_no_thumbnail(self):
        self.put("broken.png", b"not an image")
        self.assertEqual(self.client.get("/thumb/broken.png").status_code, 404)


class LimitsTests(AppTestCase):
    env = {"MAX_UPLOAD_SIZE_MB": "1"}

    def test_upload_too_large(self):
        self.login()
        with self.client.session_transaction() as sess:
            token = sess["csrf"]
        response = self.client.post(
            "/upload", data={"file": (io.BytesIO(b"x" * (2 * 1024 * 1024)), "big.bin")},
            content_type="multipart/form-data", headers={"X-CSRF-Token": token, "X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(response.status_code, 413)
        self.assertFalse((self.root / "big.bin").exists())


class BypassTests(AppTestCase):
    env = {"DOMAIN": "files.example.com", "UPLOAD_DOMAIN": "upload.example.com"}

    def test_bypass_upload(self):
        self.login()
        page = self.client.get("/upload").data.decode()
        url = re.search(r'data-url="https://upload\.example\.com([^"]+)"', page).group(1).replace("&amp;", "&")
        anonymous = self.app.test_client()
        response = anonymous.post(url, data={"file": (io.BytesIO(b"x"), "via-bypass.txt")}, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Access-Control-Allow-Origin"], "https://files.example.com")
        self.assertTrue((self.root / "via-bypass.txt").exists())
        bad = anonymous.post("/upload-bypass?token=bad", data={"file": (io.BytesIO(b"x"), "y.txt")},
                             content_type="multipart/form-data")
        self.assertEqual(bad.status_code, 401)


class GeneratedSecretsTests(unittest.TestCase):
    def test_secrets_are_generated_once_and_persisted(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
            os.environ, {"UPLOAD_FOLDER": tmp, "SECRET_KEY": "", "TOTP_SECRET": "", "LOG_LEVEL": "CRITICAL"}
        ):
            from securefilehub.config import load_settings

            first, second = load_settings(), load_settings()
            self.assertTrue(first.totp_generated)
            self.assertFalse(second.totp_generated)
            self.assertEqual(first.totp_secret, second.totp_secret)
            self.assertEqual(first.secret_key, second.secret_key)
            mode = (Path(tmp) / ".securefilehub" / "totp_secret").stat().st_mode & 0o777
            self.assertEqual(mode, 0o600)


class TranslationTests(unittest.TestCase):
    def test_every_template_string_is_translated(self):
        from securefilehub.i18n import TRANSLATIONS_DIR, parse_po

        root = Path(__file__).resolve().parent.parent / "securefilehub"
        pattern = re.compile(r"""\b_\(\s*(["'])(.+?)\1""")
        sources = list((root / "templates").glob("*.html")) + list(root.rglob("*.py"))
        messages = {m.group(2) for path in sources for m in pattern.finditer(path.read_text(encoding="utf-8"))}
        from securefilehub.routes.errors import MESSAGES

        messages |= {text for pair in MESSAGES.values() for text in pair}
        messages |= {"B", "KB", "MB", "GB", "TB"}
        catalog = parse_po((TRANSLATIONS_DIR / "ru" / "LC_MESSAGES" / "messages.po").read_text(encoding="utf-8"))
        missing = sorted(messages - catalog.keys())
        self.assertEqual(missing, [], "untranslated strings")


if __name__ == "__main__":
    unittest.main()
