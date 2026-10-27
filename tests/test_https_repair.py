import importlib.util,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('vhostcheck',Path(__file__).resolve().parents[1]/'scripts/check-postmaster-vhosts.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
class RoutingChecks(unittest.TestCase):
    def test_exact_managed_and_unrelated_wildcards(self):
        dump='# configuration file '+str(module.MANAGED)+':\nserver { server_name postmaster.justisolve.com; }\n# configuration file /etc/nginx/conf.d/other.conf:\nserver { server_name *.justisolve.com *.postmaster.justisolve.com; }\n'
        self.assertEqual(module.conflicts(dump),[])
    def test_competing_exact_and_multiple_names(self):
        dump='# configuration file /etc/nginx/conf.d/other.conf:\nserver { server_name other.example postmaster.justisolve.com; }\n'
        self.assertEqual(module.conflicts(dump),['/etc/nginx/conf.d/other.conf'])
    def test_commented_hostname_is_not_conflict(self):
        dump='# configuration file /etc/nginx/conf.d/other.conf:\n# server_name postmaster.justisolve.com;\nserver { server_name other.example; }\n'
        self.assertEqual(module.conflicts(dump),[])

class ExplicitAddressRendering(unittest.TestCase):
    def render(self,tls):
        from jinja2 import Environment,StrictUndefined
        path=Path(__file__).resolve().parents[1]/'ansible/templates/postmaster-https.conf.j2'
        return Environment(undefined=StrictUndefined).from_string(path.read_text()).render(postmaster_cert_ready=tls,ansible_all_ipv4_addresses=['154.16.170.86','172.17.0.1','127.0.0.1','154.16.170.86'])
    def test_https_joins_public_and_loopback_address_groups(self):
        result=self.render(True)
        for address in ['154.16.170.86','127.0.0.1','172.17.0.1']:
            self.assertEqual(result.count('listen '+address+':443 ssl;'),1)
            self.assertEqual(result.count('listen '+address+':80;'),1)
        self.assertIn('listen [::1]:443 ssl;',result)
        self.assertIn('listen [::]:443 ssl;',result)
        self.assertIn('proxy_pass http://127.0.0.1:18870;',result)
    def test_acme_only_has_no_premature_https(self):
        result=self.render(False)
        self.assertNotIn('443',result)
        self.assertIn('listen 154.16.170.86:80;',result)
        self.assertIn('listen 127.0.0.1:80;',result)
