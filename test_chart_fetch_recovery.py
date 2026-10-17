import unittest
from unittest.mock import patch, MagicMock
import urllib.request
import research_enhancements as r

class ChartRecoveryTests(unittest.TestCase):
    def test_public_request_preserves_headers(self):
        response=MagicMock(status_code=200)
        response.__enter__.return_value=response
        response.iter_content.return_value=[b'public response']
        request=urllib.request.Request('https://www.youtube.com/embed/abcdefghijk',headers={'User-Agent':'Bob-GoldResearch/1.0','Referer':'https://bob-private-scanner.onrender.com/'})
        with patch('requests.get',return_value=response) as get:
            self.assertEqual(r.read_public_video(request),b'public response')
        headers={k.lower():v for k,v in get.call_args.kwargs['headers'].items()}
        self.assertEqual(headers['user-agent'],'Bob-GoldResearch/1.0')
        self.assertEqual(headers['referer'],'https://bob-private-scanner.onrender.com/')
        self.assertFalse(get.call_args.kwargs['allow_redirects'])

    def test_all_five_sections_get_priority_over_neighbor_samples(self):
        moments=[{'at':i*30,'label':str(i)} for i in range(5)]
        self.assertEqual(r.neighbor_moments(moments),moments)

if __name__=='__main__':unittest.main()
