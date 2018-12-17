import os
import sys
import json
import r2pipe
import click
import argparse

MIN_SET_LEN = 8

OFFSET = {
    "InstallProtocolInterface": 0x80,
    "ReinstallProtocolInterface": 0x88,
    "UninstallProtocolInterface": 0x90,
    "HandleProtocol": 0x98,
    "RegisterProtocolNotify": 0xA8,
    "OpenProtocol": 0x118,
    "CloseProtocol": 0x120,
    "OpenProtocolInformation": 0x128,
    "ProtocolsPerHandle": 0x130,
    "LocateHandleBuffer": 0x138,
    "LocateProtocol": 0x140,
    "InstallMultipleProtocolInterfaces": 0x148,
    "UninstallMultipleProtocolInterfaces": 0x150,
}

LEA_NUM = {
    "InstallProtocolInterface": 2,
    "ReinstallProtocolInterface": 1,
    "UninstallProtocolInterface": 1,
    "HandleProtocol": 1,
    "RegisterProtocolNotify": 1,
    "OpenProtocol": 1,
    "CloseProtocol": 1,
    "OpenProtocolInformation": 1,
    "LocateHandleBuffer": 2,
    "LocateProtocol": 1,
#   "InstallMultipleProtocolInterfaces": 2,
#   "UninstallMultipleProtocolInterfaces": x,
}

class Analyser():
    def __init__(self, module_path):
        self.module_path = module_path
        self.r2 = r2pipe.open(module_path)
        self.r2.cmd("aaa")
        
        self.gBServices = {}
        self.gBServices["InstallProtocolInterface"] = []
        self.gBServices["ReinstallProtocolInterface"] = []
        self.gBServices["UninstallProtocolInterface"] = []
        self.gBServices["HandleProtocol"] = []
        self.gBServices["RegisterProtocolNotify"] = []
        self.gBServices["OpenProtocol"] = []
        self.gBServices["CloseProtocol"] = []
        self.gBServices["OpenProtocolInformation"] = []
        self.gBServices["ProtocolsPerHandle"] = []
        self.gBServices["LocateHandleBuffer"] = []
        self.gBServices["LocateProtocol"] = []
        self.gBServices["InstallMultipleProtocolInterfaces"] = []
        self.gBServices["UninstallMultipleProtocolInterfaces"] = []

        self.Protocols  = {}
        self.Protocols["All"] = [
            # {
            #   address: ...
            #   service: ...
            #   guid: ...
            # }, 
            # ...
        ]
    
    def get_info(self):
        info = json.loads(self.r2.cmd("ij"))
        return json.dumps(info, indent=2)
    
    """ 
    format: {
        func_name: func_address,
        ...
    } 
    """
    def get_funcs(self):
        funcs = {}
        json_funcs = json.loads(self.r2.cmd("aflj"))
        if len(json_funcs) == 0:
            return {}
        for func_info in json_funcs:
            funcs[func_info["name"]] = func_info["offset"]
        return funcs
    
    def get_boot_services(self):
        funcs = self.get_funcs()
        pdfs = []
        for name in funcs:
            func_info = self.r2.cmd("pdfj @ {addr}".format(addr=funcs[name]))
            pdfs.append(json.loads(func_info))
        for func_info in pdfs:
            if ("ops" in func_info):
                fcode = func_info["ops"]
                for line in fcode:
                    if ("ptr"    in line and \
                        "type"   in line and \
                        "offset" in line and \
                        "disasm" in line
                        ):
                        if (line["type"] == "ucall" and line["disasm"].find("call qword [") > -1):
                            for service_name in OFFSET:
                                ea = line["offset"]
                                if (line["ptr"] == OFFSET[service_name] and \
                                    self.gBServices[service_name].count(ea) == 0
                                    ):
                                    self.gBServices[service_name].append(ea)
    
    def list_boot_services(self):
        empty = True
        for service in self.gBServices:
            for address in self.gBServices[service]:
                empty = False
                print("\t [{0}] EFI_BOOT_SERVICES->{1}".format(hex(address), service))
        if empty:
            print(" * list is empty")

    """ return 0 if ea is end of block """
    def next_head(self, ea):
        ea = 16827769
        addresses = []
        block = json.loads(self.r2.cmd("pdbj @ {addr}".format(addr=ea)))
        for instr in block:
            addresses.append(instr["offset"])
        index = addresses.index(ea)
        if index < len(addresses) - 1:
            return addresses[index + 1]
        else:
            return 0

    """ return 0 if ea is start of block """
    def prev_head(self, ea):
        addresses = []
        block = json.loads(self.r2.cmd("pdbj @ {addr}".format(addr=ea)))
        for instr in block:
            addresses.append(instr["offset"])
        index = addresses.index(ea)
        if index > 0:
            return addresses[index - 1]
        else:
            return 0

    def get_guid(self, address):
        self.r2.cmd("s {addr}".format(addr=address))
        guid_bytes = json.loads(self.r2.cmd("pcj 16"))
        return guid_bytes
        
    def get_protocols(self):
        for service_name in self.gBServices:
            if service_name in LEA_NUM.keys():
                for address in self.gBServices[service_name]:
                    ea = address
                    lea_counter = 0
                    while (True):
                        ea = self.prev_head(ea)
                        instr = json.loads(self.r2.cmd("pdj1 @ {addr}".format(addr=ea)))[0]
                        if (instr["type"] == "lea"):
                            lea_counter += 1
                            if (lea_counter == LEA_NUM[service_name]):
                                break
                    guid_addr = instr.get("ptr")
                    if guid_addr is None:
                        continue
                    CurrentGUID = self.get_guid(guid_addr)
                    if len(set(CurrentGUID)) > MIN_SET_LEN:
                        protocol_record = {}
                        protocol_record["address"] = guid_addr
                        protocol_record["service"] = service_name
                        protocol_record["guid"] = CurrentGUID
                        if self.Protocols["All"].count(protocol_record) == 0:
                            self.Protocols["All"].append(protocol_record)

if __name__=="__main__":
    click.echo(click.style("Copyright (c) 2018 yeggor", fg="cyan"))
    program = "python " + os.path.basename(__file__)
    parser = argparse.ArgumentParser(description="UEFI module analyser",
		prog=program)
    parser.add_argument("module", 
		type=str, 
		help="the path to UEFI module")
    args = parser.parse_args()
    analyser = Analyser(args.module)
    analyser.get_boot_services()
    analyser.list_boot_services()
    analyser.get_protocols()
    print(analyser.Protocols["All"])