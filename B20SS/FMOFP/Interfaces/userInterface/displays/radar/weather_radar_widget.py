"""
Qt widget adapter for weather radar display
"""
import time
import traceback
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter
from PyQt6.QtCore import QRectF, Qt, QPointF
from .weather_radar_display import WeatherRadarDisplay
from Utils.logger.sys_logger import get_logger

logger = get_logger()

# Singleton instance with enhanced reset capability
_weather_radar_widget_instance = None
_reset_requested = False

def get_weather_radar_widget(force_reset=False):
    """Get or create the singleton instance of WeatherRadarWidget
    
    Args:
        force_reset: If True, force creation of a new instance even if one exists
    """
    global _weather_radar_widget_instance, _reset_requested
    
    # Check if reset was requested or forced
    if force_reset or _reset_requested:
        logger.warning("Reset requested for WeatherRadarWidget instance")
        
        # Clean up old instance if it exists
        if _weather_radar_widget_instance is not None:
            try:
                # Clean up display tree subscribers
                if hasattr(_weather_radar_widget_instance, 'display') and _weather_radar_widget_instance.display:
                    display = _weather_radar_widget_instance.display
                    if hasattr(display, 'tree') and display.tree:
                        tree = display.tree
                        weather_node = tree.root.get_child("weather_radar")
                        if weather_node:
                            # Clean up subscribers on visual node
                            visual_node = weather_node.get_child("visual")
                            if visual_node and hasattr(visual_node, 'subscribers'):
                                logger.warning(f"Clearing {len(visual_node.subscribers)} subscribers from visual node")
                                visual_node.subscribers.clear()
                            
                            # Clean up subscribers on data nodes
                            data_node = weather_node.get_child("data")
                            if data_node:
                                for data_type in ["precipitation", "vil", "cells"]:
                                    type_node = data_node.get_child(data_type)
                                    if type_node and hasattr(type_node, 'subscribers'):
                                        logger.warning(f"Clearing {len(type_node.subscribers)} subscribers from {data_type} node")
                                        type_node.subscribers.clear()
                
                # Stop the widget if it's running
                if _weather_radar_widget_instance.is_running():
                    _weather_radar_widget_instance.stop()
                    logger.warning("Stopped existing WeatherRadarWidget instance")
                
                # Ensure display is properly cleaned up
                if hasattr(_weather_radar_widget_instance, 'display') and _weather_radar_widget_instance.display:
                    # Call cleanup method if it exists
                    if hasattr(_weather_radar_widget_instance.display, 'cleanup'):
                        _weather_radar_widget_instance.display.cleanup()
                        logger.warning("Cleaned up display resources")
                    
                    # Reset the display property
                    _weather_radar_widget_instance._display = None
                    logger.warning("Reset display property of WeatherRadarWidget instance")
                
                # Reset the radar display data coordinator
                try:
                    from .radar_display_data_coordinator import get_radar_display_data_coordinator
                    coordinator = get_radar_display_data_coordinator()
                    coordinator.reset_data()
                    logger.warning("Reset all data in radar display data coordinator during widget reset")
                except Exception as coord_error:
                    logger.error(f"Error resetting radar display data coordinator: {coord_error}")
                    logger.error(traceback.format_exc())
                
                # Force garbage collection to clean up references
                import gc
                gc.collect()
                
                logger.warning("Cleaned up old WeatherRadarWidget instance")
            except Exception as e:
                logger.error(f"Error cleaning up old WeatherRadarWidget instance: {str(e)}")
                logger.error(traceback.format_exc())
        
        # Create new instance
        logger.warning("Creating new WeatherRadarWidget instance after reset")
        _weather_radar_widget_instance = WeatherRadarWidget()
        _reset_requested = False
        return _weather_radar_widget_instance
    
    # Normal singleton pattern
    if _weather_radar_widget_instance is None:
        logger.info("Creating new WeatherRadarWidget instance")
        _weather_radar_widget_instance = WeatherRadarWidget()
    
    return _weather_radar_widget_instance

def reset_weather_radar_widget(force_immediate=False):
    """
    Request a reset of the WeatherRadarWidget singleton instance
    
    Args:
        force_immediate: If True, reset immediately instead of waiting for next get call
    
    This function doesn't immediately reset the instance by default, but sets a flag
    that will cause the instance to be reset the next time get_weather_radar_widget is called.
    If force_immediate is True, it will reset immediately.
    """
    global _reset_requested, _weather_radar_widget_instance
    _reset_requested = True
    
    # Check current display type for logging
    from ..visual.theme_manager import get_theme_manager
    theme_manager = get_theme_manager()
    display_type = theme_manager.get_display_type("radar", "standard")
    logger.warning(f"Reset requested for WeatherRadarWidget instance (current display type: {display_type})")
    
    if force_immediate and _weather_radar_widget_instance is not None:
        try:
            # Clean up display tree subscribers
            if hasattr(_weather_radar_widget_instance, 'display') and _weather_radar_widget_instance.display:
                display = _weather_radar_widget_instance.display
                if hasattr(display, 'tree') and display.tree:
                    tree = display.tree
                    weather_node = tree.root.get_child("weather_radar")
                    if weather_node:
                        # Clean up subscribers on visual node
                        visual_node = weather_node.get_child("visual")
                        if visual_node and hasattr(visual_node, 'subscribers'):
                            logger.warning(f"Clearing {len(visual_node.subscribers)} subscribers from visual node")
                            visual_node.subscribers.clear()
                        
                        # Clean up subscribers on data nodes
                        data_node = weather_node.get_child("data")
                        if data_node:
                            for data_type in ["precipitation", "vil", "cells"]:
                                type_node = data_node.get_child(data_type)
                                if type_node and hasattr(type_node, 'subscribers'):
                                    logger.warning(f"Clearing {len(type_node.subscribers)} subscribers from {data_type} node")
                                    type_node.subscribers.clear()
            
            # Stop the widget if it's running
            if _weather_radar_widget_instance.is_running():
                _weather_radar_widget_instance.stop()
                logger.warning("Stopped existing WeatherRadarWidget instance")
            
            # Ensure display is properly cleaned up
            if hasattr(_weather_radar_widget_instance, 'display') and _weather_radar_widget_instance.display:
                # Call cleanup method if it exists
                if hasattr(_weather_radar_widget_instance.display, 'cleanup'):
                    _weather_radar_widget_instance.display.cleanup()
                    logger.warning("Cleaned up display resources during immediate reset")
                
                # Reset the display property
                _weather_radar_widget_instance._display = None
                logger.warning("Reset display property of WeatherRadarWidget instance")
            
            # Reset the radar display data coordinator
            try:
                from .radar_display_data_coordinator import get_radar_display_data_coordinator
                coordinator = get_radar_display_data_coordinator()
                coordinator.reset_data()
                logger.warning("Reset all data in radar display data coordinator during immediate widget reset")
            except Exception as coord_error:
                logger.error(f"Error resetting radar display data coordinator: {coord_error}")
                logger.error(traceback.format_exc())
            
            # Force garbage collection
            import gc
            gc.collect()
            
            # Set instance to None
            _weather_radar_widget_instance = None
            logger.warning("Immediately reset WeatherRadarWidget instance")
        except Exception as e:
            logger.error(f"Error during immediate reset of WeatherRadarWidget: {str(e)}")
            logger.error(traceback.format_exc())

class WeatherRadarWidget(QWidget):
    """Qt widget adapter for weather radar display"""
    
    def __init__(self):
        super().__init__()
        self._running = False
        
        # Check theme settings for display type
        from ..visual.theme_manager import get_theme_manager
        theme_manager = get_theme_manager()
        display_type = theme_manager.get_display_type("radar", "standard")
        logger.info(f"[WEATHER_WIDGET] Creating display with type: {display_type}")
        
        # Create appropriate display based on display type
        if display_type == "holographic":
            from .weather_radar_holographic_display import WeatherRadarHolographicDisplay
            self._display = WeatherRadarHolographicDisplay()
            logger.info("[WEATHER_WIDGET] Created holographic weather radar display")
        else:
            self._display = WeatherRadarDisplay()
            logger.info("[WEATHER_WIDGET] Created standard weather radar display")
        
        # Store the current display type for change detection
        self._current_display_type = display_type
        
        # Subscribe to update events
        from core.event_driven_communication import get_event_bus
        self.event_bus = get_event_bus()
        self.event_bus.subscribe('weather_radar_update', lambda _: self.update())
        
        # Set window properties
        self.setWindowTitle("Weather Radar Display")
        self.setGeometry(100, 100, 800, 600)
        self.setMinimumSize(800, 600)
        self.setMaximumSize(800, 600)  # Fix the size
        
        # Set window flags for proper display
        self.setWindowFlags(
            Qt.WindowType.Window |              # Regular window
            Qt.WindowType.WindowStaysOnTopHint |  # Stay on top
            Qt.WindowType.CustomizeWindowHint |   # Custom window
            Qt.WindowType.WindowTitleHint        # Show title bar
        )
        
    def paintEvent(self, event):
        """Handle Qt paint event"""
        # Check if display type has changed
        self._check_display_type_change()
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        
        # Draw radar display
        self._display.draw_radar_elements(painter, QRectF(self.rect()), {})
        
    def _check_display_type_change(self):
        """Check if display type has changed and update display if needed"""
        try:
            # Get current display type from theme manager
            from ..visual.theme_manager import get_theme_manager
            theme_manager = get_theme_manager()
            current_type = theme_manager.get_display_type("radar", "standard")
            
            # Check if display type has changed
            if current_type != self._current_display_type:
                logger.warning(f"[WEATHER_WIDGET] Display type changed from {self._current_display_type} to {current_type}, updating display")
                
                # Verify current display type
                is_holographic = False
                if self._display is not None:
                    from .weather_radar_holographic_display import WeatherRadarHolographicDisplay
                    is_holographic = isinstance(self._display, WeatherRadarHolographicDisplay)
                    logger.info(f"[WEATHER_WIDGET] Current display is {'holographic' if is_holographic else 'standard'}")
                
                # Clean up old display if needed
                if self._display is not None:
                    # First unsubscribe from any display tree nodes
                    try:
                        if hasattr(self._display, 'tree') and self._display.tree:
                            tree = self._display.tree
                            weather_node = tree.root.get_child("weather_radar")
                            if weather_node:
                                # Clean up subscribers on visual node
                                visual_node = weather_node.get_child("visual")
                                if visual_node and hasattr(visual_node, 'subscribers'):
                                    logger.warning(f"[WEATHER_WIDGET] Clearing subscribers from visual node")
                                    visual_node.subscribers.clear()
                                
                                # Clean up subscribers on data nodes
                                data_node = weather_node.get_child("data")
                                if data_node:
                                    for data_type in ["precipitation", "vil", "cells"]:
                                        type_node = data_node.get_child(data_type)
                                        if type_node and hasattr(type_node, 'subscribers'):
                                            logger.warning(f"[WEATHER_WIDGET] Clearing subscribers from {data_type} node")
                                            type_node.subscribers.clear()
                    except Exception as e:
                        logger.error(f"[WEATHER_WIDGET] Error clearing subscribers: {str(e)}")
                
                    # Then call cleanup method if it exists
                    if hasattr(self._display, 'cleanup'):
                        try:
                            self._display.cleanup()
                            logger.info("[WEATHER_WIDGET] Cleaned up old display")
                        except Exception as e:
                            logger.error(f"[WEATHER_WIDGET] Error cleaning up old display: {str(e)}")
                    
                    # Force garbage collection to clean up references
                    import gc
                    gc.collect()
                    logger.info("[WEATHER_WIDGET] Forced garbage collection after display cleanup")
                
                # Create new display based on type
                old_display = self._display
                if current_type == "holographic":
                    from .weather_radar_holographic_display import WeatherRadarHolographicDisplay
                    self._display = WeatherRadarHolographicDisplay()
                    logger.info("[WEATHER_WIDGET] Created new holographic weather radar display")
                else:
                    self._display = WeatherRadarDisplay()
                    logger.info("[WEATHER_WIDGET] Created new standard weather radar display")
                
                # Verify the new display is different from the old one
                if self._display is old_display:
                    logger.error("[WEATHER_WIDGET] Failed to create new display instance")
                    # Force creation of a new instance
                    if current_type == "holographic":
                        from .weather_radar_holographic_display import WeatherRadarHolographicDisplay
                        self._display = WeatherRadarHolographicDisplay()
                    else:
                        self._display = WeatherRadarDisplay()
                    logger.info("[WEATHER_WIDGET] Forced creation of new display instance")
                
                # Update stored display type
                self._current_display_type = current_type
                
                # Initialize the new display synchronously to ensure it's ready
                if hasattr(self._display, 'initialize_display'):
                    try:
                        # Initialize synchronously to ensure completion
                        import asyncio
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            # Create a task and wait for it to complete
                            future = asyncio.create_task(self._display.initialize_display())
                            # We can't wait here directly as it would block the UI thread
                            # Instead, we'll log that initialization is in progress
                            logger.info("[WEATHER_WIDGET] Display initialization started asynchronously")
                        else:
                            # Run directly if no loop is running
                            loop.run_until_complete(self._display.initialize_display())
                            logger.info("[WEATHER_WIDGET] Display initialized synchronously")
                    except Exception as e:
                        logger.error(f"[WEATHER_WIDGET] Error initializing new display: {str(e)}")
                        logger.error(traceback.format_exc())
                
                # Force a repaint to show the new display
                self.update()
                if hasattr(self, 'repaint'):
                    self.repaint()
                logger.info("[WEATHER_WIDGET] Forced repaint after display change")
        except Exception as e:
            logger.error(f"[WEATHER_WIDGET] Error checking display type change: {str(e)}")
            logger.error(traceback.format_exc())
        
    def mousePressEvent(self, event):
        """Handle mouse press events and pass to display for interactive elements.
        
        Args:
            event: QMouseEvent containing click information
        """
        try:
            # Convert to QPointF for more precise positioning
            pos = QPointF(event.position())
            
            # Pass to display's handler
            if self._display.handle_mouse_click(pos):
                # If the click was handled by the display, update the widget
                self.update()
                logger.info(f"[WEATHER_WIDGET] Mouse click handled at ({pos.x():.1f}, {pos.y():.1f})")
            else:
                # If not handled, call the parent class implementation
                super().mousePressEvent(event)
                
        except Exception as e:
            logger.error(f"[WEATHER_WIDGET] Error handling mouse press: {str(e)}")
            logger.error(traceback.format_exc())
            # Still call parent to ensure proper event handling
            super().mousePressEvent(event)
        
    def is_running(self):
        """Check if display is running"""
        return self._running
        
    def start(self):
        """Start the display"""
        self._running = True
        # Don't show the widget in its own window when using the legend generator
        # The display will be shown within the MFD instead
        # Position relative to other displays
        # screen = QApplication.primaryScreen().geometry()
        # self.move(screen.left() + 1750, screen.top() + 50)
        # self.show()
        
    def stop(self):
        """Stop the display"""
        self._running = False
        self.hide()
        
    async def initialize_display(self, show_window=True):
        """Initialize the display with proper sequence
        
        Args:
            show_window: Whether to show the widget window (True for standalone, False for embedded)
        """
        try:
            logger.info("[WEATHER_WIDGET] Starting display initialization")
            
            # Initialize the underlying display
            await self._display.initialize_display()
            
            # Verify initialization
            if not self._display.tree._initialized:
                logger.error("[WEATHER_WIDGET] Display tree not properly initialized")
                raise RuntimeError("Display tree initialization failed")
            
            # Set running state but NEVER show window
            self._running = True
            
            #   THIS make the weather radar display show up in its own window
            #   Commenting this out makes the weather radar display show up in the MFD only
            # Override show_window parameter - never show the window
            # if show_window:
            #     # Position relative to other displays
            #     screen = QApplication.primaryScreen().geometry()
            #     self.move(screen.left() + 1750, screen.top() + 50)
            #     self.show()
                
            logger.info("[WEATHER_WIDGET] Display initialization complete")
            
        except Exception as e:
            logger.error(f"[WEATHER_WIDGET] Error during initialization: {str(e)}")
            logger.error(traceback.format_exc())
            raise
        
    async def set_mode(self, mode):
        """Set display mode with proper initialization check"""
        try:
            # Verify initialization
            if not self._display.tree._initialized:
                logger.error("[WEATHER_WIDGET] Cannot set mode - display not initialized")
                raise RuntimeError("Display not initialized")
                
            # Use proper mode update mechanism
            mode_data = {
                'current_mode': mode.name if hasattr(mode, 'name') else str(mode),
                'mode_enum': 'weather_radarMode',
                'source_system': 'weather_radar',
                'timestamp': time.time()
            }
            
            await self._display._handle_mode_update('mode', mode_data)
            self.update()
            logger.info(f"[WEATHER_WIDGET] Mode updated to {mode_data['current_mode']}")
            
        except Exception as e:
            logger.error(f"[WEATHER_WIDGET] Error setting mode: {str(e)}")
            logger.error(traceback.format_exc())
            raise
        
    @property
    def display(self):
        """Get the underlying radar display"""
        # Check if display type has changed before returning
        self._check_display_type_change()
        return self._display
