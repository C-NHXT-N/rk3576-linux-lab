# SPDX-License-Identifier: AGPL-3.0-only
from pathlib import Path
import sys
import time
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'04-rknn-vision'))
try:
    import numpy as np
    import output_pipeline
except ImportError:output_pipeline=None


@unittest.skipIf(output_pipeline is None,'Requires NumPy/OpenCV')
class OutputTests(unittest.TestCase):
    def test_slow_encoder_keeps_every_borrowed_canvas_intact_and_ordered(self):
        class Encoder:
            def __init__(self):self.values=[];self.closed=False
            def write(self,image):
                before=image.copy();time.sleep(.015)
                np.testing.assert_array_equal(image,before)
                self.values.append(int(image[70,0,0]))
            def close(self):self.closed=True
        encoder=Encoder();stage=output_pipeline.QueuedEncoder(lambda image:encoder)
        try:
            for index in range(8):stage.draw_submit(np.full((40,96,3),index,np.uint8),[],str(index))
        finally:stage.close()
        self.assertEqual(encoder.values,list(range(8)));self.assertTrue(encoder.closed);self.assertFalse(stage.thread.is_alive())

    def test_encoder_failure_propagates_and_closes_native_resource(self):
        class Encoder:
            closed=False
            def write(self,image):raise RuntimeError('injected encode failure')
            def close(self):self.closed=True
        encoder=Encoder();stage=output_pipeline.QueuedEncoder(lambda image:encoder)
        stage.draw_submit(np.zeros((40,96,3),np.uint8),[],'failure')
        stage.thread.join(timeout=2)
        with self.assertRaisesRegex(RuntimeError,'injected encode failure'):stage.close()
        self.assertTrue(encoder.closed);self.assertFalse(stage.thread.is_alive())


if __name__=='__main__':unittest.main()
