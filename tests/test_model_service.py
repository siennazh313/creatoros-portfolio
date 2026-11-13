import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));import model_service as m
pack={'schema_version':1,'scope':{},'facts':[{'id':'E001','type':'scope'},{'id':'E002','type':'quality'},{'id':'E003','type':'dimensions'},{'id':'E004','type':'creator','creator_id':'C001','owner':'Sienna'}]}
class ModelServiceTests(unittest.TestCase):
 def test_duplicate_evidence_rejected(self):
  with self.assertRaises(ValueError):m.check_pack({**pack,'facts':[pack['facts'][0],pack['facts'][0]]})
 def test_unread_evidence_rejected(self):
  with self.assertRaises(ValueError):m.validate_report({'summary':'x','findings':[{'title':'x','explanation':'x','evidence_ids':['E999']}],'actions':[],'limitations':['x']},{'E001'},pack)
 def test_bounded_tool_flow(self):
  calls=[{'type':'function_call','name':name,'arguments':'{}','call_id':str(i)} for i,name in enumerate(['get_scope_metrics','get_dimension_contributions','get_creator_evidence'])]
  result={'summary':'待核查','findings':[{'title':'变化','explanation':'需验证','evidence_ids':['E001']}],'actions':[{'title':'核查排期','verification':'记录7日排期','priority':'P1','creator_id':'C001','evidence_ids':['E004']}],'limitations':['不能证明限流']}
  responses=iter([{'status':'completed','output':calls},{'id':'mock','status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(result)}]}]}]);out=m.analyze(pack,request_fn=lambda p:next(responses));self.assertEqual(len(out['trace']),3);self.assertEqual(out['actions'][0]['owner'],'Sienna')
 def test_unknown_tool_rejected(self):
  with self.assertRaises(ValueError):m.analyze(pack,request_fn=lambda p:{'status':'completed','output':[{'type':'function_call','name':'execute_sql','arguments':'{}','call_id':'x'}]})
 def test_incomplete_result_rejected(self):
  with self.assertRaises(m.UpstreamError):m.analyze(pack,request_fn=lambda p:{'status':'incomplete','output':[]})
 def test_nonfinite_rejected(self):
  with self.assertRaises(ValueError):m.check_pack({**pack,'scope':{'value':float('nan')}})
if __name__=='__main__':unittest.main()
