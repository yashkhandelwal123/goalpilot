import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from goalpilot.creator import Creator, digest, write_json
from goalpilot.core import UserError


def fixture():
    return {'brand':'Example','audience':'Adults','topic':'Ingredient lists','language':'English','cta':'https://example.com','research_urls':[], 'assets':[], 'facts':[{'id':'f1','text':'Synthetic roasted chickpeas','source':'Synthetic label'}]}


def package():
    return {'title':'Read the label','hook':'What is in your snack?',
        'voiceover':'Before you choose your next snack, take a moment to read the ingredient list. This fictional example lists chickpeas and salt. Those are the only ingredients we can describe from the supplied label. Compare your own pack before deciding what suits you. Explore the product page for more details.',
        'caption':'Read the label first.','claim_checks':[{'claim':'Example ingredients','source_ids':['f1']}],
        'scenes':[{'headline':'Read your label','text':'Check the ingredient list.'} for _ in range(4)]}


class CreatorTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.agent=Creator(self.root)
    def tearDown(self): self.temp.cleanup()

    def test_offline_no_network_and_no_publish(self):
        with patch('goalpilot.creator.fetch',side_effect=AssertionError('network')):
            out=self.agent.prepare(fixture(),self.root/'draft')
        manifest=json.loads((out/'manifest.json').read_text())
        self.assertTrue(manifest['offline']);self.assertFalse(manifest['publication_enabled'])
        self.assertIn('OFFLINE',(out/'voiceover.txt').read_text())
        self.assertIn('data-document-role="page"',(out/'design.html').read_text())
        with self.assertRaises(UserError):self.agent.voice(out,'')

    def test_pause_blocks_new_work(self):
        (self.root/'PAUSE').touch()
        with self.assertRaises(UserError):self.agent.prepare(fixture(),self.root/'draft')
        self.assertFalse((self.root/'draft').exists())

    def test_preserves_existing_draft(self):
        self.agent.prepare(fixture(),self.root/'draft')
        with self.assertRaises(UserError):self.agent.prepare(fixture(),self.root/'draft')

    def test_invalid_claim_reference_rejected(self):
        value=package();value['claim_checks'][0]['source_ids']=['invented']
        with self.assertRaises(UserError):Creator.validate_package(value,fixture())

    def test_long_or_short_script_rejected(self):
        value=package();value['voiceover']='Too short'
        with self.assertRaises(UserError):Creator.validate_package(value,fixture())

    def test_valid_structured_package(self):
        Creator.validate_package(package(),fixture())

    def test_unconfirmed_asset_rejected(self):
        value=fixture();value['assets']=[{'path':'missing.jpg','rights_confirmed':False}]
        path=self.root/'brief.json';write_json(path,value)
        with self.assertRaises(UserError):self.agent.brief(path)

    def test_research_respects_robots(self):
        value=fixture();value['research_urls']=['https://example.com/post']
        with patch('goalpilot.creator.fetch',return_value={'status':200,'text':'User-agent: *\nDisallow: /','content_type':'text/plain'}) as fetch:
            research=self.agent.research(value,True)
        self.assertEqual(fetch.call_count,1);self.assertEqual(research['sources'],[])
        self.assertIn('blocked',research['gaps'][0])

    @patch.dict(os.environ,{'TTS_BASE_URL':'https://example.com/v1','TTS_API_KEY':'secret'})
    def test_consent_binds_voice_model_and_exact_input(self):
        body={'input':'Original','voice':'stock','model':'test'}
        with patch('urllib.request.build_opener') as opener:
            with self.assertRaisesRegex(UserError,'Consent hash:') as error:self.agent.request('voice',body,'','TTS','/audio/speech',100)
            token=str(error.exception).split('Consent hash: ')[1]
            changed=dict(body,input='Edited')
            with self.assertRaises(UserError):self.agent.request('voice',changed,token,'TTS','/audio/speech',100)
            opener.assert_not_called()

    @patch.dict(os.environ,{'TTS_BASE_URL':'https://example.com/v1','TTS_API_KEY':'secret'})
    def test_unknown_attempt_never_automatically_retried(self):
        body={'input':'test'}
        token=digest({'stage':'voice','endpoint':'https://example.com/v1/audio/speech','body':body})
        with patch('urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect=TimeoutError('secret')
            with self.assertRaises(UserError):self.agent.request('voice',body,token,'TTS','/audio/speech',100)
            with self.assertRaisesRegex(UserError,'already attempted'):self.agent.request('voice',body,token,'TTS','/audio/speech',100)
            self.assertEqual(opener.return_value.open.call_count,1)
        self.assertNotIn('secret',(self.agent.logs/'run-log.jsonl').read_text())

    def test_draft_keeps_manifest_and_design_current(self):
        out=self.agent.prepare(fixture(),self.root/'draft')
        with patch.object(self.agent,'generate',return_value=package()):self.agent.draft(out,'consent')
        manifest=json.loads((out/'manifest.json').read_text())
        self.assertEqual(manifest['content_hash'],digest(package()))
        self.assertFalse(manifest['offline'])
        self.assertIn('What is in your snack?',(out/'design.html').read_text())
        with self.assertRaises(UserError):self.agent.draft(out,'consent')

    def test_modified_script_blocks_render_before_tools(self):
        out=self.agent.prepare(fixture(),self.root/'draft')
        with patch.object(self.agent,'generate',return_value=package()):self.agent.draft(out,'')
        (out/'voiceover.mp3').write_bytes(b'old')
        with patch.object(self.agent,'command') as command:
            with self.assertRaises(UserError):self.agent.render(out,'font.ttf')
            command.assert_not_called()

if __name__=='__main__': unittest.main()
