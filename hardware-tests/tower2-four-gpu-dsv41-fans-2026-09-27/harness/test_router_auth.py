import unittest, os, stat, tempfile, sys, importlib.util, json
from unittest.mock import patch, MagicMock

# Load source correctly
spec = importlib.util.spec_from_file_location("model_router", "/source/model-router-after.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["model_router"] = mod
spec.loader.exec_module(mod)

class TestAuthAndRequest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False)
        self.tmp.close()
        self.key_path = self.tmp.name

    def tearDown(self):
        try: os.unlink(self.key_path)
        except: pass

    def test_valid_key(self):
        with open(self.key_path, "wb") as f: f.write(b"secret")
        os.chmod(self.key_path, 0o600)
        ep = mod.Endpoint(name="t", url="http://x", priority=0, api_key_file=self.key_path)
        self.assertEqual(mod.endpoint_auth(ep), {"Authorization": "Bearer secret"})

    def test_wrong_perms(self):
        with open(self.key_path, "wb") as f: f.write(b"secret")
        os.chmod(self.key_path, 0o644)
        ep = mod.Endpoint(name="t", url="http://x", priority=0, api_key_file=self.key_path)
        with self.assertRaises(RuntimeError): mod.endpoint_auth(ep)

    def test_symlink(self):
        target = self.key_path + ".t"
        with open(target, "wb") as f: f.write(b"secret")
        os.chmod(target, 0o600)
        os.unlink(self.key_path)
        os.symlink(target, self.key_path)
        ep = mod.Endpoint(name="t", url="http://x", priority=0, api_key_file=self.key_path)
        with self.assertRaises(RuntimeError): mod.endpoint_auth(ep)
        os.unlink(target)

    def test_missing(self):
        ep = mod.Endpoint(name="t", url="http://x", priority=0, api_key_file="/no")
        with self.assertRaises(RuntimeError): mod.endpoint_auth(ep)

    def test_newline(self):
        with open(self.key_path, "wb") as f: f.write(b"sec\nret")
        os.chmod(self.key_path, 0o600)
        ep = mod.Endpoint(name="t", url="http://x", priority=0, api_key_file=self.key_path)
        with self.assertRaises(RuntimeError): mod.endpoint_auth(ep)

    def test_empty(self):
        with open(self.key_path, "wb") as f: f.write(b"")
        os.chmod(self.key_path, 0o600)
        ep = mod.Endpoint(name="t", url="http://x", priority=0, api_key_file=self.key_path)
        with self.assertRaises(RuntimeError): mod.endpoint_auth(ep)

    def test_oversized(self):
        with open(self.key_path, "wb") as f: f.write(b"x" * 4097)
        os.chmod(self.key_path, 0o600)
        ep = mod.Endpoint(name="t", url="http://x", priority=0, api_key_file=self.key_path)
        with self.assertRaises(RuntimeError): mod.endpoint_auth(ep)

    def test_directory(self):
        os.unlink(self.key_path)
        os.mkdir(self.key_path)
        ep = mod.Endpoint(name="t", url="http://x", priority=0, api_key_file=self.key_path)
        with self.assertRaises(RuntimeError): mod.endpoint_auth(ep)
        os.rmdir(self.key_path)

    def test_fifo(self):
        os.unlink(self.key_path)
        os.mkfifo(self.key_path)
        ep = mod.Endpoint(name="t", url="http://x", priority=0, api_key_file=self.key_path)
        with self.assertRaises(RuntimeError): mod.endpoint_auth(ep)
        os.unlink(self.key_path)

    def test_no_key_empty_headers(self):
        ep = mod.Endpoint(name="t", url="http://x", priority=0)
        self.assertEqual(mod.endpoint_auth(ep), {})

    def test_request_json_mock(self):
        with open(self.key_path,"wb") as f:f.write(b"secret")
        os.chmod(self.key_path,0o600)
        ep = mod.Endpoint(name="t", url="http://x", priority=0,api_key_file=self.key_path)
        mock_conn = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"ok":true}'
        mock_conn.getresponse.return_value = mock_resp
        with patch.object(mod, 'make_connection', return_value=(mock_conn, 'http')):
            mod.request_json(ep, "/health")
            mock_conn.request.assert_called_once()
            args, kwargs = mock_conn.request.call_args
            self.assertEqual(args[0], "GET")
            self.assertEqual(kwargs['headers']['Authorization'],'Bearer secret')

    def test_snapshot_no_secret(self):
        with open(self.key_path, "wb") as f: f.write(b"secret")
        os.chmod(self.key_path, 0o600)
        ep = mod.Endpoint(name="t", url="http://x", priority=0, api_key_file=self.key_path)
        state = mod.RouterState(endpoints=[ep], model_alias="m")
        snap = json.dumps(state.snapshot())
        self.assertNotIn("secret", snap)

    def test_exception_no_secret(self):
        with open(self.key_path, "wb") as f: f.write(b"secret")
        os.chmod(self.key_path, 0o644)
        ep = mod.Endpoint(name="t", url="http://x", priority=0, api_key_file=self.key_path)
        try: mod.endpoint_auth(ep)
        except RuntimeError as e: self.assertNotIn("secret", str(e))

if __name__ == "__main__":
    unittest.main()
