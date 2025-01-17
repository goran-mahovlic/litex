#!/usr/bin/env python3

# This file is Copyright (c) 2018-2019 Florent Kermarrec <florent@enjoy-digital.fr>
# This file is Copyright (c) 2018 David Shah <dave@ds0.me>
# License: BSD

import argparse

from migen import *
from migen.genlib.resetsync import AsyncResetSynchronizer

from litex.boards.platforms import ulx3s

from litex.soc.cores.clock import *
from litex.soc.integration.soc_sdram import *
from litex.soc.integration.builder import *

from litedram.modules import MT48LC16M16
from litedram.phy import GENSDRPHY

from liteeth.phy.rmii import LiteEthPHYRMII
from liteeth.mac import LiteEthMAC

# CRG ----------------------------------------------------------------------------------------------

class _CRG(Module):
    def __init__(self, platform, sys_clk_freq):
        self.clock_domains.cd_sys = ClockDomain()
        self.clock_domains.cd_sys_ps = ClockDomain(reset_less=True)
        self.clock_domains.cd_eth = ClockDomain()
        # # #

        self.cd_sys.clk.attr.add("keep")
        self.cd_sys_ps.clk.attr.add("keep")

        # clk / rst
        clk25 = platform.request("clk25")
        rst = platform.request("rst")
        platform.add_period_constraint(clk25, 40.0)

        # pll
        self.submodules.pll = pll = ECP5PLL()
        self.comb += pll.reset.eq(rst)
        pll.register_clkin(clk25, 25e6)
        pll.create_clkout(self.cd_sys, sys_clk_freq, phase=11)
        pll.create_clkout(self.cd_sys_ps, sys_clk_freq, phase=20)
        pll.create_clkout(self.cd_eth, 50e6)        
        self.specials += AsyncResetSynchronizer(self.cd_sys, rst)

        # sdram clock
        self.comb += platform.request("sdram_clock").eq(self.cd_sys_ps.clk)

        # Stop ESP32 from resetting FPGA
        wifi_gpio0 = platform.request("wifi_gpio0")
        self.comb += wifi_gpio0.eq(1)

# BaseSoC ------------------------------------------------------------------------------------------

class BaseSoC(SoCSDRAM):
    def __init__(self, device="LFE5U-85F", toolchain="diamond", **kwargs):
        platform = ulx3s.Platform(device=device, toolchain=toolchain)
        sys_clk_freq = int(50e6)
        SoCSDRAM.__init__(self, platform, clk_freq=sys_clk_freq,
                          integrated_rom_size=0x8000,
                          **kwargs)

        self.submodules.crg = _CRG(platform, sys_clk_freq)

        if not self.integrated_main_ram_size:
            self.submodules.sdrphy = GENSDRPHY(platform.request("sdram"), cl=3)
            sdram_module = MT48LC16M16(sys_clk_freq, "1:1")
            self.register_sdram(self.sdrphy,
                                sdram_module.geom_settings,
                                sdram_module.timing_settings)

# Build --------------------------------------------------------------------------------------------

# EthernetSoC --------------------------------------------------------------------------------------

class EthernetSoC(BaseSoC):
    mem_map = {
        "ethmac": 0x30000000,  # (shadow @0xb0000000)
    }
    mem_map.update(BaseSoC.mem_map)

    def __init__(self, **kwargs):
        BaseSoC.__init__(self, **kwargs)

        self.submodules.ethphy = LiteEthPHYRMII(self.platform.request("eth_clocks"),
self.platform.request("eth"))
        self.add_csr("ethphy")
        self.submodules.ethmac = LiteEthMAC(phy=self.ethphy, dw=32,
            interface="wishbone", endianness=self.cpu.endianness)
        self.add_wb_slave(self.mem_map["ethmac"], self.ethmac.bus, 0x2000)
        self.add_memory_region("ethmac", self.mem_map["ethmac"] | self.shadow_base, 0x2000)
        self.add_csr("ethmac")
        self.add_interrupt("ethmac")

        self.ethphy.crg.cd_eth_rx.clk.attr.add("keep")
        self.ethphy.crg.cd_eth_tx.clk.attr.add("keep")
        self.platform.add_period_constraint(self.ethphy.crg.cd_eth_rx.clk, 1e9/12.5e6)
        self.platform.add_period_constraint(self.ethphy.crg.cd_eth_tx.clk, 1e9/12.5e6)
 #       self.platform.add_false_path_constraints(
 #           self.crg.cd_sys.clk,        	
 #           self.ethphy.crg.cd_eth_rx.clk,
 #           self.ethphy.crg.cd_eth_tx.clk)


# Build --------------------------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="LiteX SoC on ULX3S")
    parser.add_argument("--gateware-toolchain", dest="toolchain", default="diamond",
        help='gateware toolchain to use, diamond (default) or  trellis')
    parser.add_argument("--device", dest="device", default="LFE5U-85F",
        help='FPGA device, ULX3S can be populated with LFE5U-85F (default) or LFE5U-45F')
    builder_args(parser)
    parser.add_argument("--with-ethernet", action="store_true",
help="enable Ethernet support")
    soc_sdram_args(parser)
    args = parser.parse_args()

#    soc = BaseSoC(device=args.device, toolchain=args.toolchain, **soc_sdram_argdict(args))
#    builder = Builder(soc, **builder_argdict(args))
#    builder.build()
    cls = EthernetSoC if args.with_ethernet else BaseSoC
    soc = cls(**soc_sdram_argdict(args))
    builder = Builder(soc, **builder_argdict(args))
    builder.build()

if __name__ == "__main__":
    main()
