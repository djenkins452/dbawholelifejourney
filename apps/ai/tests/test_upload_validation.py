"""
Tests for the shared multimodal upload validator (apps/ai/upload_validation.py).

Proves the ONE validation layer both chat transports call: byte-sniffing (not
declared MIME), size, count, base64 integrity, and data-URI tolerance.
"""
import base64

from django.test import SimpleTestCase

from apps.ai.upload_validation import (
    MAX_IMAGE_SIZE,
    UploadValidationError,
    sniff_image_type,
    validate_images_list,
)

# Minimal valid magic-byte headers (padded past the 12-byte sniff floor).
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
GIF = b"GIF89a" + b"\x00" * 16
WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 8


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("utf-8")


class SniffTests(SimpleTestCase):
    def test_recognizes_each_allowed_type(self):
        self.assertEqual(sniff_image_type(PNG), "image/png")
        self.assertEqual(sniff_image_type(JPEG), "image/jpeg")
        self.assertEqual(sniff_image_type(GIF), "image/gif")
        self.assertEqual(sniff_image_type(WEBP), "image/webp")

    def test_rejects_non_image_bytes(self):
        self.assertIsNone(sniff_image_type(b"<html>not an image</html>"))
        self.assertIsNone(sniff_image_type(b"%PDF-1.7 not an image....."))
        self.assertIsNone(sniff_image_type(b"tiny"))


class ValidateImagesListTests(SimpleTestCase):
    def test_empty_is_ok(self):
        self.assertEqual(validate_images_list(None), [])
        self.assertEqual(validate_images_list([]), [])

    def test_valid_images_normalized_to_sniffed_mime(self):
        out = validate_images_list([(_b64(PNG), "image/png"), (_b64(JPEG), "image/jpeg")])
        self.assertEqual([m for _, m in out], ["image/png", "image/jpeg"])

    def test_declared_mime_is_ignored_in_favor_of_bytes(self):
        # Client LIES: declares png, but sends jpeg bytes → normalized to jpeg.
        out = validate_images_list([(_b64(JPEG), "image/png")])
        self.assertEqual(out[0][1], "image/jpeg")

    def test_spoofed_image_is_rejected(self):
        # Declares image/png but the bytes are not any allowed image.
        with self.assertRaises(UploadValidationError):
            validate_images_list([(_b64(b"#!/bin/sh\nrm -rf /"), "image/png")])

    def test_invalid_base64_rejected(self):
        with self.assertRaises(UploadValidationError):
            validate_images_list([("!!!not-base64!!!", "image/png")])

    def test_oversize_rejected(self):
        big = _b64(JPEG[:4] + b"\x00" * (MAX_IMAGE_SIZE + 1))
        with self.assertRaises(UploadValidationError):
            validate_images_list([(big, "image/jpeg")])

    def test_too_many_rejected(self):
        many = [(_b64(PNG), "image/png")] * 6
        with self.assertRaises(UploadValidationError) as ctx:
            validate_images_list(many)
        self.assertEqual(ctx.exception.status, 400)

    def test_data_uri_prefix_tolerated(self):
        payload = "data:image/png;base64," + _b64(PNG)
        out = validate_images_list([(payload, "image/png")])
        self.assertEqual(out[0][1], "image/png")

    def test_malformed_tuple_rejected(self):
        with self.assertRaises(UploadValidationError):
            validate_images_list(["just-a-string"])
