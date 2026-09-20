import unittest
from sim_bridge.fdm_receiver import FdmPoseProtocol

class FdmAltitudeTest(unittest.TestCase):
    def test_terrain_height_does_not_change_absolute_aircraft_altitude(self):
        receiver=FdmPoseProtocol(lambda pose:None,0,153)
        # Same aircraft absolute height, different ground clearances.
        over_valley=receiver._parse(b'1,49,34,200,0,0,0,60,984.2519685')
        over_hill=receiver._parse(b'2,49,34,200,0,0,0,60,164.04199475')
        self.assertEqual(over_valley['altitude_asl_m'],353)
        self.assertEqual(over_hill['altitude_asl_m'],353)
        self.assertAlmostEqual(over_valley['altitude_agl_m'],300,places=4)
        self.assertAlmostEqual(over_hill['altitude_agl_m'],50,places=4)

    def test_restart_reads_new_home_elevation(self):
        home=[153]
        receiver=FdmPoseProtocol(lambda pose:None,0,lambda:home[0])
        packet=b'1,49,34,1.3,0,0,0,0,4.2650919'
        self.assertAlmostEqual(receiver._parse(packet)['altitude_asl_m'],154.3)
        home[0]=420
        self.assertAlmostEqual(receiver._parse(packet)['altitude_asl_m'],421.3)
