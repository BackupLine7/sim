import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from sim_bridge.__main__ import PoseHub
class Control:
 def __init__(self): self.messages=[]; self.rc=None
 def submit(self,message): self.messages.append(message)
class Socket:
 def __init__(self,message):self.message=message;self.errors=[]
 def __aiter__(self):return self.iterate()
 async def iterate(self):yield self.message
 async def send(self,message):self.errors.append(message)
class OwnershipTests(unittest.IsolatedAsyncioTestCase):
 async def test_observer_release_cannot_claim_or_interrupt_control(self):
  control=Control();hub=PoseHub(control);owner=object();hub.operator=owner
  socket=Socket('{"type":"command","action":"release"}')
  await hub.register(socket)
  self.assertIs(hub.operator,owner)
  self.assertEqual(control.messages,[])
  self.assertEqual(socket.errors,[])
 async def test_release_without_owner_does_not_acquire_control(self):
  control=Control();hub=PoseHub(control)
  await hub.register(Socket('{"type":"command","action":"release"}'))
  self.assertIsNone(hub.operator)
  self.assertEqual(control.messages,[])
 async def test_explicit_manual_command_takes_over(self):
  control=Control();hub=PoseHub(control);previous=Socket('');hub.operator=previous
  current=Socket('{"type":"command","action":"manual"}')
  await hub.register(current)
  self.assertEqual(control.messages,[{'type':'command','action':'manual'}])
  self.assertEqual(current.errors,[])
  self.assertIn('control_lost',previous.errors[0])
 async def test_old_owner_sticks_cannot_take_control_back(self):
  control=Control();hub=PoseHub(control);owner=object();hub.operator=owner
  await hub.register(Socket('{"type":"command","action":"stick","roll":1,"pitch":0,"throttle":1}'))
  self.assertEqual(control.messages,[])
  self.assertIs(hub.operator,owner)
if __name__=='__main__':unittest.main()
