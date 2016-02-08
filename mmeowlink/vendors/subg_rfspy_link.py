
# Based on decoding-carelink/decocare/link.py

import array
import binascii
import logging
import time

from decocare.lib import hexdump, CRC8

from .. fourbysix import FourBySix
from .. exceptions import InvalidPacketReceived, CommsException, SubgRfspyVersionNotSupported

from serial_interface import SerialInterface
from serial_rf_spy import SerialRfSpy

io  = logging.getLogger( )
log = io.getChild(__name__)

class SubgRfspyLink(SerialInterface):
  TIMEOUT = 1
  REPETITION_DELAY = 0
  MAX_REPETITION_BATCHSIZE = 250

  # Which version of subg_rfspy do we support?
  SUPPORTED_VERSIONS = ["0.6"]

  RFSPY_ERRORS = {
    0xaa: "Timeout",
    0xbb: "Command Interrupted",
    0xcc: "Zero Data"
  }

  def __init__(self, device):
    self.timeout = 1
    self.device = device
    self.speed = 19200
    self.channel = 0

    self.open()

  def check_setup(self):
    self.serial_rf_spy = SerialRfSpy(self.serial)

    self.serial_rf_spy.sync()

    # Check it's a SerialRfSpy device by retrieving the firmware version
    self.serial_rf_spy.send_command(self.serial_rf_spy.CMD_GET_VERSION, timeout=1)
    version = self.serial_rf_spy.get_response(timeout=1).split(' ')[1]

    log.debug( 'serial_rf_spy Firmare version: %s' % version)

    if version not in self.SUPPORTED_VERSIONS:
      raise SubgRfspyVersionNotSupported("Your subg_rfspy version (%s) is not in the supported version list: %s" % (version, "".join(self.SUPPORTED_VERSIONS)))

  def write( self, string, repetitions=1, repetition_delay=0, timeout=None ):
    rf_spy = self.serial_rf_spy

    remaining_messages = repetitions
    while remaining_messages > 0:
      if remaining_messages < self.MAX_REPETITION_BATCHSIZE:
        transmissions = remaining_messages
      else:
        transmissions = self.MAX_REPETITION_BATCHSIZE
      remaining_messages = remaining_messages - transmissions

      crc = CRC8.compute(string)

      message = chr(self.channel) + chr(transmissions - 1) + chr(repetition_delay) + FourBySix.encode(string)

      rf_spy.do_command(rf_spy.CMD_SEND_PACKET, message, timeout=timeout)

  def read( self, timeout=None ):
    rf_spy = self.serial_rf_spy

    if timeout is None:
      timeout = self.timeout

    timeout_ms = timeout * 1000
    timeout_ms_high = int(timeout_ms / 256)
    timeout_ms_low = int(timeout_ms - (timeout_ms_high * 256))

    resp = rf_spy.do_command(SerialRfSpy.CMD_GET_PACKET, chr(self.channel) + chr(timeout_ms_high) + chr(timeout_ms_low), timeout=timeout + 1)
    if not resp:
      raise CommsException("Did not get a response, or response is too short: %s" % len(resp))

    # If the length is 1, then it means we've received an error
    if len(resp) == 1:
      raise CommsException("Received an error response %s" % self.RFSPY_ERRORS[ resp[0] ])

    decoded = FourBySix.decode(resp[2:])

    return decoded