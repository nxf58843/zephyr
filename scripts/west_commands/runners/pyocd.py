# Copyright (c) 2017 Linaro Limited.
#
# SPDX-License-Identifier: Apache-2.0

'''Runner for pyOCD .'''

import os
from os import path

from runners.core import ZephyrBinaryRunner, RunnerCaps, \
    BuildConfiguration

DEFAULT_PYOCD_GDB_PORT = 3333
DEFAULT_PYOCD_TELNET_PORT = 4444


class PyOcdBinaryRunner(ZephyrBinaryRunner):
    '''Runner front-end for pyOCD.'''

    def __init__(self, cfg, target,
                 pyocd='pyocd',
                 flash_addr=0x0, erase=False, flash_opts=None,
                 flash_format=None,
                 gdb_port=DEFAULT_PYOCD_GDB_PORT,
                 telnet_port=DEFAULT_PYOCD_TELNET_PORT, tui=False,
                 pyocd_config=None,
                 board_id=None, daparg=None, frequency=None, tool_opt=None, wsl_path=None):
        super().__init__(cfg)

        default = path.join(cfg.board_dir, 'support', 'pyocd.yaml')
        if path.exists(default):
            self.pyocd_config = default
        else:
            self.pyocd_config = None


        self.target_args = ['-t', target]
        ''' if running in WSL, call py.exe to run pyOCD in Windows '''
        ''' most debuggers are not accessible directly in WSL, but '''
        ''' the pyOCD server is still accessible to gdb inside WSL '''
        self.pyocd = [wsl_path, '-m', pyocd] if wsl_path is not None else [pyocd]
        self.wsl_path = wsl_path
        self.flash_addr_args = ['-a', hex(flash_addr)] if flash_addr else []
        self.erase = erase
        self.flash_format = flash_format
        self.gdb_cmd = [cfg.gdb] if cfg.gdb is not None else None
        self.gdb_port = gdb_port
        self.telnet_port = telnet_port
        self.tui_args = ['-tui'] if tui else []
        self.hex_name = cfg.hex_file
        self.bin_name = cfg.bin_file 
        self.elf_name = cfg.elf_file

        pyocd_config_args = []

        if self.pyocd_config is not None:
            pyocd_config_args = ['--config', self.pyocd_config]

        self.pyocd_config_args = pyocd_config_args

        board_args = []
        if board_id is not None:
            board_args = ['-u', board_id]
        self.board_args = board_args

        daparg_args = []
        if daparg is not None:
            daparg_args = ['-da', daparg]
        self.daparg_args = daparg_args

        frequency_args = []
        if frequency is not None:
            frequency_args = ['-f', frequency]
        self.frequency_args = frequency_args

        tool_opt_args = []
        if tool_opt is not None:
            tool_opt_args = [tool_opt]
        self.tool_opt_args = tool_opt_args

        self.flash_extra = flash_opts if flash_opts else []

    @classmethod
    def name(cls):
        return 'pyocd'

    @classmethod
    def capabilities(cls):
        return RunnerCaps(commands={'flash', 'debug', 'debugserver', 'attach'},
                          flash_addr=True, erase=True)

    @classmethod
    def do_add_parser(cls, parser):
        parser.add_argument('--target', required=True,
                            help='target override')

        parser.add_argument('--daparg',
                            help='Additional -da arguments to pyocd tool')
        parser.add_argument('--pyocd', default='pyocd',
                            help='path to pyocd tool, default is pyocd')
        parser.add_argument('--flash-opt', default=[], action='append',
                            help='''Additional options for pyocd flash,
                            e.g. --flash-opt="-e=chip" to chip erase''')
        parser.add_argument('--flash-format', 
                            help='''flash image format bin/hex/elf,
                            default will use elf by extension''')
        parser.add_argument('--frequency',
                            help='SWD clock frequency in Hz')
        parser.add_argument('--gdb-port', default=DEFAULT_PYOCD_GDB_PORT,
                            help='pyocd gdb port, defaults to {}'.format(
                                DEFAULT_PYOCD_GDB_PORT))
        parser.add_argument('--telnet-port', default=DEFAULT_PYOCD_TELNET_PORT,
                            help='pyocd telnet port, defaults to {}'.format(
                                DEFAULT_PYOCD_TELNET_PORT))
        parser.add_argument('--tui', default=False, action='store_true',
                            help='if given, GDB uses -tui')
        parser.add_argument('--board-id',
                            help='ID of board to flash, default is to prompt')
        parser.add_argument('--tool-opt',
                            help='''Additional options for pyocd Commander,
                            e.g. \'--script=user.py\' ''')
        parser.add_argument('--wsl-path', 
                            help='path to windows python executable to get around USB restrictions in WSL')

    @classmethod
    def do_create(cls, cfg, args):
        build_conf = BuildConfiguration(cfg.build_dir)
        flash_addr = cls.get_flash_address(args, build_conf)

        ret = PyOcdBinaryRunner(
            cfg, args.target,
            pyocd=args.pyocd,
            flash_addr=flash_addr, erase=args.erase, flash_opts=args.flash_opt,
            flash_format=args.flash_format,
            gdb_port=args.gdb_port, telnet_port=args.telnet_port, tui=args.tui,
            board_id=args.board_id, daparg=args.daparg,
            frequency=args.frequency,
            tool_opt=args.tool_opt, wsl_path=args.wsl_path)

        daparg = os.environ.get('PYOCD_DAPARG')
        if not ret.daparg_args and daparg:
            ret.logger.warning('PYOCD_DAPARG is deprecated; use --daparg')
            ret.logger.debug('--daparg={} via PYOCD_DAPARG'.format(daparg))
            ret.daparg_args = ['-da', daparg]

        return ret

    def port_args(self):
        return ['-p', str(self.gdb_port), '-T', str(self.telnet_port)]

    def do_run(self, command, **kwargs):
        self.require(self.pyocd[0])
        if command == 'flash':
            self.flash(**kwargs)
        else:
            self.debug_debugserver(command, **kwargs)

    def flash(self, **kwargs):
        fformat_args = []    
        if self.flash_format == 'hex':
            fname = self.hex_name
            fformat_args = ['--format', 'hex']
        elif self.flash_format == 'bin':
            fname = self.bin_name
            fformat_args = ['--format', 'bin']
        elif self.flash_format == 'elf':
            fname = self.elf_name
            fformat_args = ['--format', 'elf']
        else:
            fname = self.elf_name
        if not os.path.isfile(fname):
            raise ValueError(
                'Cannot flash; ({}) file not found. '.format(fname))
        ''' If running in WSL, the path needs to be a windows path '''
        ''' Convert to relative path first so the drive mount point '''
        ''' does not need to be converted '''
        if self.wsl_path is not None: 
            fname = os.path.relpath(fname)
            fname = fname.replace('/', '\\')

        erase_method = 'chip' if self.erase else 'sector'

        cmd = (self.pyocd +
               ['flash'] +
               self.pyocd_config_args +
               ['-e', erase_method] +
               fformat_args +
               self.flash_addr_args +
               self.daparg_args +
               self.target_args +
               self.board_args +
               self.frequency_args +
               self.tool_opt_args +
               self.flash_extra +
               [fname])

        self.logger.info('Flashing file: {}'.format(fname))
        self.check_call(cmd)

    def log_gdbserver_message(self):
        self.logger.info('pyOCD GDB server running on port {}'.
                         format(self.gdb_port))

    def debug_debugserver(self, command, **kwargs):
        server_cmd = (self.pyocd +
                      ['gdbserver'] +
                      self.daparg_args +
                      self.port_args() +
                      self.target_args +
                      self.board_args +
                      self.frequency_args +
                      self.tool_opt_args)

        if command == 'debugserver':
            self.log_gdbserver_message()
            self.check_call(server_cmd)
        else:
            if self.gdb_cmd is None:
                raise ValueError('Cannot debug; gdb is missing')
            if self.elf_name is None:
                raise ValueError('Cannot debug; elf is missing')
            client_cmd = (self.gdb_cmd +
                          self.tui_args +
                          [self.elf_name] +
                          ['-ex', 'target remote :{}'.format(self.gdb_port)])
            if command == 'debug':
                client_cmd += ['-ex', 'monitor halt',
                               '-ex', 'monitor reset',
                               '-ex', 'load']

            self.require(client_cmd[0])
            self.log_gdbserver_message()
            self.run_server_and_client(server_cmd, client_cmd)
