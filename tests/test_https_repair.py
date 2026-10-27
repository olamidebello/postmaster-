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
