"""
User CLI for Flight Management Operating Flight Program
"""

import asyncio
import os
import sys
import time
import queue
import sys
import threading
import xml.etree.ElementTree as ET
import traceback
import click
import asyncio
import importlib
import FMOFP.Utils.common.fetching as fetching
from FMOFP.Utils.common.paths import paths
from FMOFP.MIL_STD_1553B.Messaging import send1553Msg
from FMOFP.Utils.logger.sys_logger import get_logger
from FMOFP.Utils.common.system_states import userCLIStates
from FMOFP.Utils.common.system_state_manager import SystemStateManager
from FMOFP.local_messaging.routing.handlers.system_message_handlers.RadarMessageHandler import RadarMessageHandler
from FMOFP.local_messaging.routing.handlers.sync_handler.AsyncMessageHandler import AsyncMessageHandler
from FMOFP.Systems.radarManagement.radar_enums import RadarMode
from FMOFP.Systems.radarManagement.weather.weather_radar import weather_radarMode
from FMOFP.Systems.radarManagement.radarControl import get_radar_management_system
from FMOFP.local_messaging.command_word_map import RADAR_TYPES, COMMAND_REGISTRY

logger = get_logger()

@click.group()
def cli():
    pass

@cli.command()
def test():
    """Run system tests"""
    cli = get_user_cli()
    cli._process_command("test")

class UserCLI:
    _instance = None
    _test_lock = threading.Lock()
    _test_running = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        logger.info(f"UserCLI __init__ called. Thread ID: {threading.get_ident()}")
        self.paths = paths()
        self.command_queue = queue.Queue()
        self.output_queue = queue.Queue()
        self.command_processed = threading.Event()
        self.command_received = threading.Event()
        self.command_printed = threading.Event()
        self.sendMsg = send1553Msg()
        self.command_processed.set()  # Initially, no command is being processed
        self.prompt_printed = False
        self.debugging = False
        self.commandInterface = False
        self.stop_threads = False
        self.command = ""
        self.cli_enabled = False
        self.state_manager = SystemStateManager()
        self.prompt_shown = False
        self.cli_threads = []
        self.load_config()

        # These will be initialized later when needed
        self._radar_message_handler = None
        self._async_handler = None
        self._radar_handler = None

    @property
    def radar_message_handler(self):
        if not self._radar_message_handler:
            self._radar_message_handler = RadarMessageHandler()
        return self._radar_message_handler

    @property
    def async_handler(self):
        if not self._async_handler:
            self._async_handler = AsyncMessageHandler()
        return self._async_handler

    @property
    def radar_handler(self):
        if not self._radar_handler:
            self._radar_handler = RadarMessageHandler()
        return self._radar_handler

    def initialize(self):
        logger.info(f"UserCLI initialize called. Thread ID: {threading.get_ident()}")
        if self._initialized:

            return

        # Initialize handlers only when needed
        self._radar_message_handler = RadarMessageHandler()
        self._async_handler = AsyncMessageHandler()
        self._radar_handler = RadarMessageHandler()

        self._initialized = True
        logger.info(f"UserCLI initialized. Thread ID: {threading.get_ident()}")

    def start(self):
        logger.info("UserCLI: Starting user interface")
        while True:
            try:
                time.sleep(10)
                pass
            except KeyboardInterrupt:
                logger.info("UserCLI: Exiting user interface")
                sys.exit(0)

    def send(self):
        logger.info("UserCLI: Initiating send command process")
        radar_options = {
            1: "weather_radar",
            2: "tfr_radar",
            3: "sar_radar",
            4: "targeting_radar",
            5: "aewc_radar"
        }
        radar_num = int(input("Which radar would you like to select? (1-5)? "))
        selected_radar = radar_options.get(radar_num)

        logger.info(f"  Which command would you like to send?")
        logger.info(f"  1) Radar System Status Request")
        logger.info(f"  2) Radar Mode Change Request")
        command_num = int(input("Enter command (1-2)? "))

        if command_num == 1:
            logger.info(f"UserCLI: Sending status request for {selected_radar}")
            try:
                from FMOFP.Systems.radarManagement.radarControl import get_radar_management_system
                rms = get_radar_management_system()
                status = None
                for radar in rms.radars.values():
                    radar_type = type(radar).__name__.lower()
                    if selected_radar.replace('_radar', '') in radar_type:
                        status = radar.get_status()
                        break
                if status:
                    logger.info(f"--- {selected_radar} status ---")
                    for key, val in status.items():
                        logger.info(f"  {key}: {val}")
                else:
                    logger.info(f"No radar found matching '{selected_radar}'")
            except Exception as e:
                logger.error(f"Error retrieving status for {selected_radar}: {str(e)}")
        elif command_num == 2:
            mode = input("Enter mode (STANDBY, SURVEILLANCE, MAPPING): ")
            logger.info(f"UserCLI: Sending mode change request for {selected_radar}: {mode}")
            try:
                self.radar_handler.send_radar_request(selected_radar, "mode_change", mode)
            except Exception as e:
                logger.error(f"Error in send command: {str(e)}")
                logger.info(f"Error: {str(e)}")
        else:
            logger.info("Invalid command number")

    def load_config(self):
        try:
            config_file = os.path.join(fetching.fetch_fmofp_path(), 'startupConfiguration.xml')
            tree = ET.parse(config_file)
            root = tree.getroot()
            logging_config = root.find('logging')
            if logging_config is not None:
                command_interface_elem = logging_config.find('commandInterface')
                debugging_elem = logging_config.find('debugging')
                prompt_printed_elem = logging_config.find('promptPrinted')

                self.cli_enabled = command_interface_elem is not None and command_interface_elem.text.lower() == 'true'
                self.debugging = debugging_elem is not None and debugging_elem.text.lower() == 'true'
                self.prompt_printed = prompt_printed_elem is not None and prompt_printed_elem.text.lower() == 'true'

            command_registry_file = os.path.join('FMOFP', 'local_messaging', 'messageConfigurations', 'command_registry.xml')
            command_registry_tree = ET.parse(command_registry_file)
            command_registry_root = command_registry_tree.getroot()
            command_words_config = command_registry_root.find('command_words')
            if command_words_config is not None:
                for command in command_words_config.findall('command'):
                    name = command.get('name')
                    value = command.get('value')
                    COMMAND_REGISTRY[name] = value

            logger.info(f"Configuration loaded successfully from {config_file} and {command_registry_file}")
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            traceback.print_exc()

    def commandLineThreadControl(self):
        logger.info(f"Entering commandLineThreadControl. Thread ID: {threading.get_ident()}")
        try:
            while not self.stop_threads:
                if not self.command_received.is_set():
                    self.command_received.wait()

                if self.command_received.is_set():
                    self.command_received.clear()
                    self.command_processed.set()

                if not self.command_processed.is_set():
                    self.command_processed.wait()

                if self.command_processed.is_set():
                    self.command_processed.clear()
                    self.command_printed.set()

                if self.command_received.is_set() and self.command_processed.is_set():
                    self.command_received.clear()
                    self.command_processed.clear()
                    self.command_printed.set()
        except Exception as error:
            logger.error(f"Exception occurred in commandLineThreadControl. Thread ID: {threading.get_ident()}", exc_info=True)
        finally:
            logger.info(f"Exiting commandLineThreadControl. Thread ID: {threading.get_ident()}")

    def _process_command(self, command):
        """Process a single command."""
        if not command:
            return
        logger.info(f"Processing command '{command}'")
        try:
            if command.startswith("help"):
                self._print_help()

            elif command == "test":
                # Check if test is already running
                if UserCLI._test_running:
                    logger.info("A test is already running. Please wait for it to complete.")
                    self.output_queue.put("\nA test is already running. Please wait for it to complete.")
                    return

                # Set test running flag
                UserCLI._test_running = True

                try:
                    # Clear any existing output
                    while not self.output_queue.empty():
                        self.output_queue.get()

                    # Use asyncio.run() instead of manually managing event loop

                    # Choose which test to run
                    test_options = {
                        "1": "Combined Precipitation & VIL Flow Test",
                        "2": "FMS System Test",
                        "3": "Flight Control System Test",
                        "4": "Predefined Messages Test",
                        "5": "Weather Radar Test (All Modes)",
                        "6": "TFR Radar Test (All Modes)",
                        "7": "SAR Radar Test (All Modes)",
                        "8": "Targeting Radar Test (All Modes)",
                        "9": "AEWC Radar Test (All Modes)"
                    }

                    print("\nAvailable tests:")
                    for key, name in test_options.items():
                        print(f"{key}) {name}")

                    test_choice = input(f"\nSelect a test to run (1-{len(test_options)}): ")

                    if test_choice == "1":
                        asyncio.run(self.combined_precipitation_vil_flow_test())
                    elif test_choice == "2":
                        asyncio.run(self.fms_system_test())
                    elif test_choice == "3":
                        asyncio.run(self.flight_control_system_test())
                    elif test_choice == "4":
                        asyncio.run(self.predefined_messages_test())
                    elif test_choice == "5":
                        asyncio.run(self.weather_radar_all_modes_test())
                    elif test_choice == "6":
                        asyncio.run(self.tfr_radar_all_modes_test())
                    elif test_choice == "7":
                        asyncio.run(self.sar_radar_all_modes_test())
                    elif test_choice == "8":
                        asyncio.run(self.targeting_radar_all_modes_test())
                    elif test_choice == "9":
                        asyncio.run(self.aewc_radar_all_modes_test())
                    else:
                        logger.error(f"Invalid test selection: {test_choice}")
                        self.output_queue.put(f"\nInvalid test selection: {test_choice}")

                except Exception as e:
                        # Log error and return immediately
                        logger.error(f"Test failed: {str(e)}")
                        self.output_queue.put(f"\nTest failed: {str(e)}")
                        return

                except Exception as e:
                    logger.error(f"Error running tests: {str(e)}", exc_info=True)
                    self.output_queue.put(f"\nError running tests: {str(e)}")
                finally:
                    # Reset test running flag
                    UserCLI._test_running = False

            elif command == "get_import_statement":
                function_name = input("Enter a function name: ")
                file_path = input("Enter a file path: ")
                self.get_import_statement(function_name, file_path)
            elif command == "list_tables":
                self.list_tables()
            elif command == "get_table":
                table_name = input("Enter a table name: ")
                self.get_table(table_name)
            else:
                self.output_queue.put("Unknown command. Type 'help' to see a list of available commands.")
        except Exception as error:
            logger.error(f"Exception occurred in _process_command: {error}", exc_info=True)
            self.output_queue.put(f"Error processing command: {str(error)}")
        finally:
            # Ensure command is marked as processed
            self.command_processed.set()

    # In the _process_command function within userCLI.py
    async def weather_radar_display_visual_test(self):
        """Run the weather radar display test"""
        try:
            # Import test module dynamically to avoid circular imports
            test_module = importlib.import_module('FMOFP.Tests.weather_radar_display_visual_test')
            test_class = getattr(test_module, 'TestWeatherRadarDisplayVisual')

            # Setup test environment
            logger.info("Setting up test environment")
            test_suite = test_class()

            # Run the full test sequence
            logger.info("\nStarting Weather Radar Display Test...")
            await test_suite.run_tests()

            # Process test results
            logger.info("\nTest completed successfully!")

        except Exception as e:
            logger.error(f"Test suite error: {str(e)}", exc_info=True)
            # Re-raise to ensure failure is caught by caller
            raise

    async def vil_display_flow_test(self):
        """Run the VIL display flow test"""
        try:
            # Import test module dynamically to avoid circular imports
            test_module = importlib.import_module('FMOFP.Tests.vil_display_flow_test')
            test_class = getattr(test_module, 'TestVILDisplayFlow')

            # Setup test environment
            logger.info("Setting up test environment")
            test_suite = test_class()

            # Run the full test sequence
            logger.info("\nStarting VIL Display Flow Test...")
            await test_suite.run_tests()

            # Process test results
            logger.info("\nTest completed successfully!")

        except Exception as e:
            logger.error(f"Test suite error: {str(e)}", exc_info=True)
            # Re-raise to ensure failure is caught by caller
            raise

    async def combined_precipitation_vil_flow_test(self):
        """Run the combined precipitation and VIL display flow test"""
        try:
            # Import test module dynamically to avoid circular imports
            test_module = importlib.import_module('FMOFP.Tests.combined_precipitation_vil_flow_test')
            test_class = getattr(test_module, 'TestCombinedPrecipitationVILFlow')

            # Setup test environment
            logger.info("Setting up test environment")
            test_suite = test_class()

            # Run the full test sequence
            logger.info("\nStarting Combined Precipitation and VIL Display Flow Test...")
            await test_suite.run_tests()

            # Process test results
            logger.info("\nTest completed successfully!")

        except Exception as e:
            logger.error(f"Test suite error: {str(e)}", exc_info=True)
            # Re-raise to ensure failure is caught by caller
            raise

    async def precipitation_display_flow_test(self):
        """Run the precipitation display flow test"""
        try:
            # Import test module dynamically to avoid circular imports
            test_module = importlib.import_module('FMOFP.Tests.precipitation_display_flow_test')
            test_class = getattr(test_module, 'TestPrecipitationDisplayFlow')

            # Setup test environment
            logger.info("Setting up test environment")
            test_suite = test_class()

            # Run the full test sequence
            logger.info("\nStarting Precipitation Display Flow Test...")
            await test_suite.run_tests()

            # Process test results
            logger.info("\nTest completed successfully!")

        except Exception as e:
            logger.error(f"Test suite error: {str(e)}", exc_info=True)
            # Re-raise to ensure failure is caught by caller
            raise

    async def echo_top_display_flow_test(self):
        """Run the Echo Top display flow test"""
        try:
            # Import test module dynamically to avoid circular imports
            test_module = importlib.import_module('FMOFP.Tests.echo_top_display_flow_test')
            test_class = getattr(test_module, 'TestEchoTopDisplayFlow')

            # Setup test environment
            logger.info("Setting up test environment")
            test_suite = test_class()

            # Run the full test sequence
            logger.info("\nStarting Echo Top Display Flow Test...")
            await test_suite.run_tests()

            # Process test results
            logger.info("\nTest completed successfully!")

        except Exception as e:
            logger.error(f"Test suite error: {str(e)}", exc_info=True)
            # Re-raise to ensure failure is caught by caller
            raise


    # In the _process_command function within userCLI.py
    async def weather_radar_display_test(self):
        """Run the weather radar display test"""
        try:
            # Import test module dynamically to avoid circular imports
            test_module = importlib.import_module('FMOFP.Tests.weather_radar_display_test')
            test_class = getattr(test_module, 'TestWeatherRadarDisplay')

            # Setup test environment
            logger.info("Setting up test environment")
            test_suite = test_class()

            # Run the full test sequence
            logger.info("\nStarting Weather Radar Display Test...")
            await test_suite.run_tests()

            # Process test results
            logger.info("\nTest completed successfully!")

        except Exception as e:
            logger.error(f"Test suite error: {str(e)}", exc_info=True)
            # Re-raise to ensure failure is caught by caller
            raise

    async def weather_radar_end_to_end_test(self):
        """Run the weather radar end-to-end test"""
        try:
            # Import test module dynamically to avoid circular imports
            test_module = importlib.import_module('FMOFP.Tests.weather_radar_end_to_end_test')
            test_class = getattr(test_module, 'TestWeatherRadarEndToEnd')

            # Setup test environment
            logger.info("Setting up test environment")
            test_suite = test_class()

            # Run the full test sequence
            logger.info("\nStarting Weather Radar End-to-End Test...")
            await test_suite.run_tests()

            # Process test results
            logger.info("\nTest completed successfully!")

        except Exception as e:
            logger.error(f"Test suite error: {str(e)}", exc_info=True)
            # Re-raise to ensure failure is caught by caller
            raise

    #   precipitation_system_test
    async def precipitation_system_test(self):
        """Run the precipitation system test"""
        try:
            # Import test module dynamically to avoid circular imports
            test_module = importlib.import_module('FMOFP.Tests.precipitation_system_test')
            test_class = getattr(test_module, 'TestPrecipitationSystem')

            # Setup test environment
            logger.info("Setting up test environment")
            test_suite = test_class()

            # Run the full test sequence
            logger.info("\nStarting  Test.")
            await test_suite.run_tests()

            # Process test results
            logger.info("\nTest completed successfully!")

        except Exception as e:
            logger.error(f"Test suite error: {str(e)}", exc_info=True)
            # Re-raise to ensure failure is caught by caller
            raise

    # The userCLI function
    async def vil_system_test(self):
        """Run the VIL system test"""
        try:
            # Import test module dynamically to avoid circular imports
            test_module = importlib.import_module('FMOFP.Tests.vil_system_test')
            test_class = getattr(test_module, 'TestVILSystem')

            # Setup test environment
            logger.info("Setting up test environment")
            test_suite = test_class()

            # Run the full test sequence
            logger.info("\nStarting VIL System Test...")
            await test_suite.run_tests()

            # Process test results
            logger.info("\nTest completed successfully!")

        except Exception as e:
            logger.error(f"Test suite error: {str(e)}", exc_info=True)
            # Re-raise to ensure failure is caught by caller
            raise

    async def fms_system_test(self):
        """Run the Flight Management System test"""
        try:
            # Import test module dynamically to avoid circular imports
            test_module = importlib.import_module('FMOFP.Tests.fms_system_test')
            test_class = getattr(test_module, 'TestFMSSystem')

            # Setup test environment
            logger.info("Setting up test environment")
            test_suite = test_class()

            # Run the full test sequence
            logger.info("\nStarting FMS System Test...")
            await test_suite.run_tests()

            # Process test results
            logger.info("\nTest completed successfully!")

        except Exception as e:
            logger.error(f"Test suite error: {str(e)}", exc_info=True)
            # Re-raise to ensure failure is caught by caller
            raise

    async def flight_control_system_test(self):
        """Run the Flight Control System test"""
        try:
            # Import test module dynamically to avoid circular imports
            test_module = importlib.import_module('FMOFP.Tests.flight_control_system_test')
            test_class = getattr(test_module, 'TestFlightControlSystem')

            # Setup test environment
            logger.info("Setting up test environment")
            test_suite = test_class()

            # Run the full test sequence
            logger.info("\nStarting Flight Control System Test...")
            await test_suite.run_tests()

            # Process test results
            logger.info("\nTest completed successfully!")

        except Exception as e:
            logger.error(f"Test suite error: {str(e)}", exc_info=True)
            # Re-raise to ensure failure is caught by caller
            raise

    #   test_targeting_radar_mode_change
    async def test_sar_radar_mode_change(self):
        """Run the SAR radar mode change test"""
        try:
            # Import test module dynamically to avoid circular imports
            test_module = importlib.import_module('FMOFP.Tests.sar_radar_mode_change_system_test')
            test_class = getattr(test_module, 'TestSARRadarModeChangeSystem')

            # Setup test environment
            logger.info("Setting up test environment")
            test_suite = test_class()

            # Run the full test sequence
            logger.info("\nStarting SAR Radar Mode Change Test...")
            await test_suite.test_sar_radar_mode_changes()

            # Process test results
            logger.info("\nTest completed successfully!")

        except Exception as e:
            logger.error(f"Test suite error: {str(e)}", exc_info=True)
            # Re-raise to ensure failure is caught by caller
            raise

    async def targeting_radar_mode_change(self):
        """Run the targeting radar mode change test"""
        try:
            # Import test module dynamically to avoid circular imports
            test_module = importlib.import_module('FMOFP.Tests.targeting_radar_mode_change_system_test')
            test_class = getattr(test_module, 'TestTargetingRadarModeChangeSystem')

            # Setup test environment
            logger.info("Setting up test environment")
            test_suite = test_class()

            # Run the full test sequence
            logger.info("\nStarting Targeting Radar Mode Change Test...")
            await test_suite.test_targeting_radar_mode_changes()

            # Process test results
            logger.info("\nTest completed successfully!")

        except Exception as e:
            logger.error(f"Test suite error: {str(e)}", exc_info=True)
            # Re-raise to ensure failure is caught by caller
            raise

    async def aewc_radar_mode_change(self):
        """Run the AEWC radar mode change test"""
        try:
            # Import test module dynamically to avoid circular imports
            test_module = importlib.import_module('FMOFP.Tests.aewc_radar_mode_change_system_test')
            test_class = getattr(test_module, 'TestAEWCRadarModeChangeSystem')

            # Setup test environment
            logger.info("Setting up test environment")
            test_suite = test_class()

            # Run the full test sequence
            logger.info("\nStarting AEWC Radar Mode Change Test...")
            await test_suite.test_aewc_radar_mode_changes()

            # Process test results
            logger.info("\nTest completed successfully!")

        except Exception as e:
            logger.error(f"Test suite error: {str(e)}", exc_info=True)
            # Re-raise to ensure failure is caught by caller
            raise

    async def tfr_radar_mode_change(self):
        """Run the TFR radar mode change test"""
        try:
            # Import test module dynamically to avoid circular imports
            test_module = importlib.import_module('FMOFP.Tests.tfr_radar_mode_change_system_test')
            test_class = getattr(test_module, 'TestTFRRadarModeChangeSystem')

            # Setup test environment
            logger.info("Setting up test environment")
            test_suite = test_class()

            # Run the full test sequence
            logger.info("\nStarting TFR Radar Mode Change Test...")
            await test_suite.test_tfr_radar_mode_changes()

            # Process test results
            logger.info("\nTest completed successfully!")

        except Exception as e:
            logger.error(f"Test suite error: {str(e)}", exc_info=True)
            # Re-raise to ensure failure is caught by caller
            raise

    async def predefined_messages_test(self):
        """Run the Comprehensive Predefined Messages Test"""
        try:
            # Import test module dynamically to avoid circular imports
            test_module = importlib.import_module('FMOFP.Tests.predefined_messages_test')
            test_class = getattr(test_module, 'PredefinedMessagesTest')

            # Setup test environment
            logger.info("Setting up test environment")
            test_suite = test_class()


            logger.info("\nStarting Comprehensive Predefined Messages Test...")
            result = await test_suite.run_tests()

            # Process test results
            logger.info("\nTest completed!")


            # Process test results
            if result:
                logger.info("\nPredefined Messages Test completed successfully!")
            else:
                logger.error("\nPredefined Messages Test failed!")
                raise RuntimeError("Predefined Messages Test failed")

        except Exception as e:
            logger.error(f"Test suite error: {str(e)}", exc_info=True)
            # Re-raise to ensure failure is caught by caller
            raise

    async def weather_radar_all_modes_test(self):
        """Run the comprehensive Weather Radar modes test"""
        try:
            # Import test module dynamically to avoid circular imports
            test_module = importlib.import_module('FMOFP.Tests.radar_tests.weather_radar_test')
            test_class = getattr(test_module, 'WeatherRadarTest')

            # Setup test environment
            logger.info("Setting up test environment")
            test_suite = test_class()

            # Run the full test sequence
            logger.info("\nStarting Comprehensive Weather Radar Mode Test...")
            result = await test_suite.run_tests()

            # Process test results
            if result:
                logger.info("\nWeather Radar Test completed successfully!")
            else:
                logger.error("\nWeather Radar Test failed!")
                raise RuntimeError("Weather Radar Test failed")

        except Exception as e:
            logger.error(f"Test suite error: {str(e)}", exc_info=True)
            # Re-raise to ensure failure is caught by caller
            raise

    async def tfr_radar_all_modes_test(self):
        """Run the comprehensive TFR Radar modes test"""
        try:
            # Import test module dynamically to avoid circular imports
            test_module = importlib.import_module('FMOFP.Tests.radar_tests.tfr_radar_test')
            test_class = getattr(test_module, 'TFRRadarTest')

            # Setup test environment
            logger.info("Setting up test environment")
            test_suite = test_class()

            # Run the full test sequence
            logger.info("\nStarting Comprehensive TFR Radar Mode Test...")
            result = await test_suite.run_tests()

            # Process test results
            if result:
                logger.info("\nTFR Radar Test completed successfully!")
            else:
                logger.error("\nTFR Radar Test failed!")
                raise RuntimeError("TFR Radar Test failed")

        except Exception as e:
            logger.error(f"Test suite error: {str(e)}", exc_info=True)
            # Re-raise to ensure failure is caught by caller
            raise

    async def sar_radar_all_modes_test(self):
        """Run the comprehensive SAR Radar modes test"""
        try:
            # Import test module dynamically to avoid circular imports
            test_module = importlib.import_module('FMOFP.Tests.radar_tests.sar_radar_test')
            test_class = getattr(test_module, 'SARRadarTest')

            # Setup test environment
            logger.info("Setting up test environment")
            test_suite = test_class()

            # Run the full test sequence
            logger.info("\nStarting Comprehensive SAR Radar Mode Test...")
            result = await test_suite.run_tests()

            # Process test results
            if result:
                logger.info("\nSAR Radar Test completed successfully!")
            else:
                logger.error("\nSAR Radar Test failed!")
                raise RuntimeError("SAR Radar Test failed")

        except Exception as e:
            logger.error(f"Test suite error: {str(e)}", exc_info=True)
            # Re-raise to ensure failure is caught by caller
            raise

    async def targeting_radar_all_modes_test(self):
        """Run the comprehensive Targeting Radar modes test"""
        try:
            # Import test module dynamically to avoid circular imports
            test_module = importlib.import_module('FMOFP.Tests.radar_tests.targeting_radar_test')
            test_class = getattr(test_module, 'TargetingRadarTest')

            # Setup test environment
            logger.info("Setting up test environment")
            test_suite = test_class()

            # Run the full test sequence
            logger.info("\nStarting Comprehensive Targeting Radar Mode Test...")
            result = await test_suite.run_tests()

            # Process test results
            if result:
                logger.info("\nTargeting Radar Test completed successfully!")
            else:
                logger.error("\nTargeting Radar Test failed!")
                raise RuntimeError("Targeting Radar Test failed")

        except Exception as e:
            logger.error(f"Test suite error: {str(e)}", exc_info=True)
            # Re-raise to ensure failure is caught by caller
            raise

    async def aewc_radar_all_modes_test(self):
        """Run the comprehensive AEWC Radar modes test"""
        try:
            # Import test module dynamically to avoid circular imports
            test_module = importlib.import_module('FMOFP.Tests.radar_tests.aewc_radar_test')
            test_class = getattr(test_module, 'AEWCRadarTest')

            # Setup test environment
            logger.info("Setting up test environment")
            test_suite = test_class()

            # Run the full test sequence
            logger.info("\nStarting Comprehensive AEWC Radar Mode Test...")
            result = await test_suite.run_tests()

            # Process test results
            if result:
                logger.info("\nAEWC Radar Test completed successfully!")
            else:
                logger.error("\nAEWC Radar Test failed!")
                raise RuntimeError("AEWC Radar Test failed")

        except Exception as e:
            logger.error(f"Test suite error: {str(e)}", exc_info=True)
            # Re-raise to ensure failure is caught by caller
            raise

    async def weather_radar_node_test(self):
        """Run the weather radar node test"""
        try:
            # Import test module dynamically to avoid circular imports
            test_module = importlib.import_module('FMOFP.Tests.weather_radar_node_test')
            test_class = getattr(test_module, 'TestWeatherRadarMessageFlow')

            # Setup test environment
            logger.info("Setting up test environment")
            test_suite = test_class()

            # Run the full test sequence
            logger.info("\nStarting Weather Radar Node Test...")
            await test_suite.run_tests()

            # Process test results
            logger.info("\nTest completed successfully!")

        except Exception as e:
            logger.error(f"Test suite error: {str(e)}", exc_info=True)
            # Re-raise to ensure failure is caught by caller
            raise

    async def weather_radar_visual_test(self):
        """Run the weather radar visual test"""
        try:
            # Import test module dynamically to avoid circular imports
            test_module = importlib.import_module('FMOFP.Tests.weather_radar_visual_test')
            test_class = getattr(test_module, 'TestWeatherRadarVisual')

            # Setup test environment
            logger.info("Setting up test environment")
            test_suite = test_class()

            # Run the full test sequence
            logger.info("\nStarting Weather Radar Visual Test...")
            await test_suite.run_tests()

            # Process test results
            logger.info("\nTest completed successfully!")

        except Exception as e:
            logger.error(f"Test suite error: {str(e)}", exc_info=True)
            # Re-raise to ensure failure is caught by caller
            raise

    async def test_display_individual_mode(self):
        """Run the individual display mode test"""
        try:
            # Import test module dynamically to avoid circular imports
            test_module = importlib.import_module('FMOFP.Tests.display_individual_mode_test')
            test_class = getattr(test_module, 'TestDisplayIndividualMode')

            # Setup test environment
            logger.info("Setting up test environment")
            test_suite = test_class()

            # Run the full test sequence
            logger.info("\nStarting Individual Display Mode Test...")
            await test_suite.test_display_system()  # Test each display type with each mode individually

            # Process test results
            logger.info("\nIndividual Display Mode Test completed successfully!")

        except Exception as e:
            logger.error(f"Test suite error: {str(e)}", exc_info=True)
            # Re-raise to ensure failure is caught by caller
            raise

    async def TestWeatherRadarModeChange(self):
        """Run system-level weather radar mode change test"""
        try:
            # Run the system-level test
            logger.info("\nStarting System-Level Weather Radar Mode Change Test...")
            system_test_module = importlib.import_module('FMOFP.Tests.weather_radar_mode_change_system_test')
            system_test_class = getattr(system_test_module, 'TestWeatherRadarModeChangeSystem')
            system_test_suite = system_test_class()
            await system_test_suite.test_weather_radar_mode_changes()

            # Process test results
            logger.info("\nAll Weather Radar Mode Change Tests completed successfully!")

        except Exception as e:
            logger.error(f"Test suite error: {str(e)}", exc_info=True)
            # Re-raise to ensure failure is caught by caller
            raise

    def _handle_test_results(self, results):
        """Handle and display test results."""
        logger.info("Processing test results")
        self.output_queue.put("\nTest Results:")
        for result in results:
            status_symbol = "✓" if result['status'] == 'PASS' else "✗"
            msg = f"{status_symbol} {result['name']}"
            logger.info(msg)
            self.output_queue.put(msg)
            if result['message']:
                logger.info(f"    {result['message']}")
                self.output_queue.put(f"    {result['message']}")

        # Summary
        pass_count = sum(1 for r in results if r['status'] == 'PASS')
        total_count = len(results)
        summary = f"\nSummary: {pass_count}/{total_count} tests passed"
        logger.info(summary)
        self.output_queue.put(summary)

    def get_commands(self):
        """Get commands from user input."""
        try:
            while not self.stop_threads:
                if self.state_manager.cli_state_node is not None:
                    if self.cli_enabled and userCLIStates.ACCEPTING_COMMANDS.name in self.state_manager.get_cli_state().name:
                        if not self.prompt_shown:
                            print("\nEnter a command: ", end='', flush=True)
                            self.prompt_shown = True
                        command = input()
                        if command:
                            # Handle test command directly
                            if command == "test":
                                self._process_command(command)
                            else:
                                self.command_queue.put(command)
                                self.command_received.set()
                            self.prompt_shown = False
                        time.sleep(0.1)
                    else:
                        time.sleep(0.1)
                else:
                    time.sleep(0.1)
        except Exception as error:
            logger.error("Exception occurred in get_commands", exc_info=True)
        finally:
            pass

    def output_commands(self):
        try:
            while not self.stop_threads:
                if self.cli_enabled:
                    if not self.output_queue.empty():
                        result = self.output_queue.get()
                        logger.info(result)
                        self.prompt_shown = False
                    if self.command_printed.is_set():
                        self.command_printed.clear()
                        self.command_processed.set()
                    time.sleep(0.1)
                else:
                    time.sleep(0.1)
        except Exception as error:
            logger.error("Exception occurred in output_commands", exc_info=True)

    def enable_cli(self):
        self.cli_enabled = True
        self.state_manager.set_cli_state(userCLIStates.ACCEPTING_COMMANDS)
        logger.info(f"CLI enabled and accepting commands. Thread ID: {threading.get_ident()}")

    def disable_cli(self):
        self.state_manager.set_cli_state(userCLIStates.NOT_ACCEPTING_COMMANDS)
        logger.info(f"CLI disabled and not accepting commands. Thread ID: {threading.get_ident()}")

    def stop_cli_threads(self):
        logger.info(f"Stopping CLI threads. Thread ID: {threading.get_ident()}")
        self.stop_threads = True
        for thread in self.cli_threads:
            thread.join()
        self.cli_threads = []
        logger.info(f"CLI threads stopped. Thread ID: {threading.get_ident()}")

    def is_cli_ready(self):
        return self._initialized and self.cli_enabled and all(thread.is_alive() for thread in self.cli_threads)

    def _get_radar_options(self):
        options = [f"  {i+1}) {radar_type}" for i, radar_type in enumerate(RADAR_TYPES)]
        return "  Which radar would you like to send a request?\n" + "\n".join(options)

    def _get_radar_selection(self):
        radar_types = {str(i+1): radar_type for i, radar_type in enumerate(RADAR_TYPES)}

        while True:
            radar_input = input("Which radar would you like to select? (1-5)? ")
            radar_name = radar_types.get(radar_input)
            if radar_name:
                return radar_name
            else:
                self.output_queue.put("Invalid radar selected. Please try again.")

    def _get_command_options(self):
        return "\n".join([
            "  Available commands:",
            "  1) Radar System Status Request",
            "  2) Radar Mode Change Request"
        ])

    def _get_command_selection(self):
        """Get command selection from user input."""
        command_types = {
            "1": "status",
            "2": "mode_change"
        }

        while True:
            command_input = input("Which command would you like to send? (1-2)? ")
            command = command_types.get(command_input)
            if command:
                return command
            else:
                self.output_queue.put("Invalid command selected. Please try again.")

    def _get_mode_options(self, radar_name):
        if radar_name.lower() == "weather_radar":
            return [mode.name for mode in weather_radarMode], weather_radarMode
        else:
            return [mode.name for mode in RadarMode], RadarMode

    def _display_radar_state(self, radar_name):
        logger.info(f"UserCLI: Displaying current state for {radar_name}")
        radar_management_system = get_radar_management_system()
        radar = radar_management_system.radars.get(radar_name)
        if radar:
            state = radar.get_status()
            self.output_queue.put(f"Current {radar_name} State: {state}")
        else:
            self.output_queue.put(f"{radar_name} not found in the system.")
        self.command_processed.set()

    def generate_random_data_word(self):
        import random
        return ''.join(random.choice('01') for _ in range(16))

    def _print_help(self):
        help_message = "\n".join([
            "Available commands:",
            "  send       - Send radar commands",
            "  msg        - Run basic messaging test",
            "  test       - Run all system tests",
            "  test_1553b - Run comprehensive MIL-STD-1553B protocol tests",
            "  help       - Show this help message"
        ])
        self.output_queue.put(help_message)

    def _print_command_help(self, command_name):
        help_messages = {
            "send": "send - Send commands to radar systems",
            "test": "test - Run all system tests including weather radar, messaging, and MIL-STD-1553B tests"
        }
        self.output_queue.put(help_messages.get(command_name, f"Unknown command '{command_name}'. Type 'help' to see a list of available commands."))

    def get_import_statement(self, function_name, file_path):
        pass

    def get_table(self, table_name):
        table_data = self.sdb.read_table(table_name)
        if table_data:
            self.output_queue.put(f"Table '{table_name}' contents:\n{table_data}")
        else:
            self.output_queue.put("Invalid radar selected. Please try again.")

    def check_health(self) -> bool:
        """
        Check the health of the UserCLI.
        :return: True if the UserCLI is healthy, False otherwise.
        """
        return self._initialized and self.cli_enabled and all(thread.is_alive() for thread in self.cli_threads)

    def list_tables(self):
        """
        List available tables in the database.
        Note: The current DatabaseManager class doesn't have a method to list all tables.
        This is a placeholder that needs to be implemented.
        """
        self.output_queue.put("Table listing functionality not yet implemented")

    def process_commands(self):
        """Main command processing entry point"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            self.get_commands()
        except Exception as e:
            logger.error(f"Error running async process commands: {e}", exc_info=True)
        finally:
            try:
                loop.close()
            except Exception as e:
                logger.error(f"Error closing event loop: {e}", exc_info=True)

# Lazy initialization of singleton
_user_cli_instance = None

def get_user_cli():
    global _user_cli_instance
    if _user_cli_instance is None:
        _user_cli_instance = UserCLI()
    return _user_cli_instance

if __name__ == '__main__':
    cli()
    cli = get_user_cli()
    cli.process_commands()
