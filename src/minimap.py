import tkinter as tk
import threading
import queue
import math
import time
import asyncio
import win32gui
from loguru import logger
from wizwalker import XYZ
from wizwalker.memory.memory_objects.window import Window 
from src.sprinty_client import SprintyClient
from src.teleport_math import navmap_tp

class MiniMap:
    def __init__(self, clients, update_interval=0.2, radius=2000, size=200):
        """
        Args:
            clients: List of WizWalker client instances
            update_interval: How often to update the map (in seconds)
            radius: The detection radius around the player (in game units)
            size: The size of the minimap canvas (in pixels)
        """
        # Core properties
        self.clients = clients
        self.update_interval = update_interval
        self.radius = radius
        self.size = size
        self.scale_factor = size / (radius * 2) * 0.9  # Zoom out factor
        self.north_oriented = True
        self.show_grid = True
        
        # UI customization
        self.background_color = '#000000'  # Black background
        self.border_color = '#FFFFFF'      # White border
        self.inner_color = '#111111'       # Dark gray inner circle
        self.inner_alpha = 0.3             # Inner circle transparency
        
        # UI components and state
        self.windows = []
        self.canvases = []
        self.root = None
        self.running = False
        
        # Thread-safe communication
        self.teleport_queue = queue.Queue()
        self.entity_queue = queue.Queue()
        self.command_queue = queue.Queue()
        self.update_thread = None

    async def process_teleport_queue(self):
        """Process any pending teleport requests in the queue"""
        while not self.teleport_queue.empty():
            try:
                client, position, entity_name = self.teleport_queue.get_nowait()
                if hasattr(client, 'teleport'):
                    await navmap_tp(client, position)
                else:
                    pass
            except Exception:
                pass

    def _handle_zoom(self, direction):
        """Handle zoom in/out on the minimap"""
        if direction == "in":
            self.scale_factor = min(self.scale_factor * 1.25, 0.05)  # Limit max zoom
        else:  # "out"
            self.scale_factor = max(self.scale_factor / 1.25, 0.005)  # Limit min zoom
        
        # Update all canvases with new scale factor
        for canvas in self.canvases:
            if hasattr(canvas, 'entity_positions'):
                canvas.entity_positions.clear()  # Force redraw

    def _create_windows(self):
        """Create minimap windows for each client"""
        # Clear any existing windows
        for window in self.windows:
            try:
                window.destroy()
            except Exception:
                pass
        
        self.windows = []
        self.canvases = []
        
        # Create a new window for each client
        for i, client in enumerate(self.clients):
            # Check if client is valid
            if client is None or isinstance(client, int) or not hasattr(client, 'title'):
                self._create_fallback_window(i, client)
                continue
            
            try:
                # Create the main window with transparent background
                root = tk.Toplevel()
                root.title("")
                root.geometry(f"{self.size}x{self.size + 20}+{20 + i*50}+{20 + i*50}")
                root.attributes('-topmost', True)
                root.attributes('-alpha', 0.85)
                root.configure(bg=self.background_color)
                root.overrideredirect(True)
                root.wm_attributes('-transparentcolor', self.background_color)
                
                # Create a frame and canvas
                frame = tk.Frame(root, bg=self.background_color)
                frame.pack(fill=tk.BOTH, expand=True)
                
                canvas = tk.Canvas(frame, width=self.size, height=self.size, 
                                  bg=self.background_color, highlightthickness=0)
                canvas.pack(fill=tk.BOTH, expand=False)
                
                # Create circular minimap elements
                canvas.create_oval(2, 2, self.size-2, self.size-2, 
                                  fill=self.inner_color, outline='', 
                                  tags="background", stipple='gray12')
                
                canvas.create_oval(2, 2, self.size-2, self.size-2, 
                                  outline=self.border_color, width=2, tags="border")
                
                # Add client title with shadow effect
                client_title = client.title if hasattr(client, 'title') and client.title else f'Client {i+1}'
                
                shadow_label = tk.Label(root, text=client_title, fg='black', 
                                      bg=self.background_color, font=('Arial', 12, 'bold'))
                shadow_label.place(x=3, y=self.size+1)
                
                title_label = tk.Label(root, text=client_title, fg=self.border_color, 
                                      bg=self.background_color, font=('Arial', 12, 'bold'))
                title_label.place(x=2, y=self.size)
                
                # Add drag functionality
                self._add_drag_functionality(root)
                self._update_zoom_indicator()
                
                self.windows.append(root)
                self.canvases.append(canvas)

                for window in self.windows:
                    window.bind("+", lambda event: self._handle_zoom("in"))
                    window.bind("-", lambda event: self._handle_zoom("out"))
                    window.bind("=", lambda event: self._handle_zoom("in"))  # For easier access without shift
                    window.bind("g", lambda event: self._toggle_grid())  # Add grid toggle
                
            except Exception:
                self._create_fallback_window(i, client)
    
    def _create_fallback_window(self, i, client):
        """Create a fallback window if we can't get the client window position"""
        # Create the main window
        root = tk.Toplevel()
        root.title("")
        root.geometry(f"{self.size}x{self.size + 20}+{20 + i*50}+{20 + i*50}")
        root.attributes('-topmost', True)
        root.attributes('-alpha', 0.85)
        root.configure(bg=self.background_color)
        root.overrideredirect(True)
        root.wm_attributes('-transparentcolor', self.background_color)
        
        # Create frame and canvas
        frame = tk.Frame(root, bg=self.background_color)
        frame.pack(fill=tk.BOTH, expand=True)
        
        canvas = tk.Canvas(frame, width=self.size, height=self.size, 
                          bg=self.background_color, highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=False)
        
        # Create circular minimap elements
        canvas.create_oval(2, 2, self.size-2, self.size-2, 
                          fill=self.inner_color, outline='', 
                          tags="background", stipple='gray12')
        
        canvas.create_oval(2, 2, self.size-2, self.size-2, 
                          outline=self.border_color, width=2, tags="border")
        
        # Add client title with shadow effect
        client_title = client.title if hasattr(client, 'title') else f'Client {i+1}'
        
        shadow_label = tk.Label(root, text=client_title, fg='black', 
                              bg=self.background_color, font=('Arial', 12, 'bold'))
        shadow_label.place(x=3, y=self.size+1)
        
        title_label = tk.Label(root, text=client_title, fg=self.border_color, 
                              bg=self.background_color, font=('Arial', 12, 'bold'))
        title_label.place(x=2, y=self.size)
        
        # Add drag functionality
        self._add_drag_functionality(root)
        
        self.windows.append(root)
        self.canvases.append(canvas)
    
    def _toggle_grid(self):
        """Toggle grid visibility"""
        self.show_grid = not self.show_grid
        
        # Force redraw of all canvases
        for canvas in self.canvases:
            if hasattr(canvas, 'entity_positions'):
                canvas.entity_positions.clear()  # Force redraw
    
    def _add_drag_functionality(self, window):
        """Add the ability to drag the window by clicking anywhere on it"""
        window.manually_positioned = False
        
        def start_drag(event):
            window.x, window.y = event.x, event.y
        
        def drag(event):
            x = window.winfo_x() - window.x + event.x
            y = window.winfo_y() - window.y + event.y
            window.geometry(f"+{x}+{y}")
            window.manually_positioned = True
        
        window.bind("<ButtonPress-1>", start_drag)
        window.bind("<B1-Motion>", drag)
        
        # Add click handler for entity teleportation
        for i, canvas in enumerate(self.canvases):
            if canvas.winfo_id() == window.winfo_id():
                canvas.bind("<ButtonPress-1>", lambda event, c=canvas: self._handle_minimap_click(event, c))
                
                # Add mouse wheel binding for zoom
                canvas.bind("<MouseWheel>", lambda event: self._handle_mouse_wheel(event))

    def _handle_mouse_wheel(self, event):
        """Handle mouse wheel events for zooming"""
        # Prevent event propagation
        event.widget.focus_set()
        
        # On Windows, event.delta is positive when scrolling up and negative when scrolling down
        if event.delta > 0:
            self._handle_zoom("in")
        else:
            self._handle_zoom("out")
        
        # Prevent further propagation
        return "break"
    
    def _handle_minimap_click(self, event, canvas):
        """Handle clicks on the minimap to teleport to entities"""
        if not hasattr(canvas, 'entity_positions'):
            return
            
        # Find the closest entity to the click position
        click_x, click_y = event.x, event.y
        closest_entity = None
        closest_distance = float('inf')
        client_idx = None
        click_radius = 15  # 15px click radius
        
        # Iterate through all entity positions
        for entity_tag, entity_data in canvas.entity_positions.items():
            try:
                coords = canvas.coords(entity_tag)
                if coords:
                    # Calculate center of the oval and distance from click
                    entity_x = (coords[0] + coords[2]) / 2
                    entity_y = (coords[1] + coords[3]) / 2
                    distance = math.sqrt((click_x - entity_x)**2 + (click_y - entity_y)**2)
                    
                    # Update closest entity if this one is closer
                    if distance < closest_distance and distance < click_radius:
                        closest_entity = (entity_data['position'], entity_data['name'])
                        closest_distance = distance
                        client_idx = entity_data['client_idx']
            except:
                continue
                
        # Queue navmap teleport to the closest entity
        if closest_entity and client_idx is not None and client_idx < len(self.clients):
            position, entity_name = closest_entity
            client = self.clients[client_idx]
            
            # Add to teleport queue
            self.teleport_queue.put((client, position, entity_name))
    
    
    def _update_loop(self):
        """Background thread to gather entity data from clients"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        active_teleport_tasks = {}
        
        try:
            while self.running:
                try:
                    # Process teleport requests
                    while not self.teleport_queue.empty():
                        try:
                            client, position, entity_name = self.teleport_queue.get_nowait()
                            if client and position:
                                # Cancel any existing teleport task for this client
                                if client in active_teleport_tasks and not active_teleport_tasks[client].done():
                                    active_teleport_tasks[client].cancel()
                                
                                # Create and track new teleport task
                                active_teleport_tasks[client] = asyncio.ensure_future(navmap_tp(client, position))
                        except queue.Empty:
                            break
                        except Exception:
                            pass
                    
                    # Gather and queue entity data
                    all_client_data = loop.run_until_complete(self._gather_entities())
                    if all_client_data:
                        self.entity_queue.put(all_client_data)
                    
                    time.sleep(0.1)
                    
                except Exception:
                    time.sleep(1)
        finally:
            # Cancel any remaining teleport tasks
            for task in active_teleport_tasks.values():
                if not task.done():
                    task.cancel()
            
            try:
                loop.close()
            except:
                pass

    async def _gather_entities(self):
        """Gather nearby entities for each client and put them in the queue for rendering"""
        all_client_data = []
        
        for client_idx, client in enumerate(self.clients):
            # Skip invalid clients
            if client is None or isinstance(client, int) or not hasattr(client, 'body'):
                all_client_data.append(None)
                continue
                
            try:
                # Get player position and global ID
                player_pos = await client.body.position()
                player_orient = await client.body.orientation()
                player_gid = await client.client_object.global_id_full()
                
                entity_data = {
                    'player': {
                        'pos': player_pos,
                        'orient': player_orient,
                        'gid': player_gid
                    },
                    'entities': []
                }
                
                # Get all entities for this client
                try:
                    sprinter = SprintyClient(client)
                    entities = await sprinter.get_base_entity_list()
                    effective_radius = 2000  # Reduced radius for minimap zoom
                    
                    for entity in entities:
                        try:
                            # Get entity position and ID
                            entity_pos = await entity.location()
                            entity_gid = await entity.global_id_full()
                            
                            # Skip if it's the player entity
                            if entity_gid == player_gid:
                                continue
                                
                            # Calculate distance to player
                            distance = math.sqrt(
                                (entity_pos.x - player_pos.x) ** 2 + 
                                (entity_pos.y - player_pos.y) ** 2
                            )
                            
                            # Only include entities within the effective radius
                            if distance <= effective_radius:
                                # Get entity name
                                entity_name = "Unknown"
                                try:
                                    obj_template = await entity.object_template()
                                    entity_name = await obj_template.object_name()
                                    
                                    # Skip certain entities
                                    if entity_name in ["Cinematic Camera", "Basic Positional", "Basic Ambient"]:
                                        continue
                                except:
                                    pass
                                    
                                entity_data['entities'].append({
                                    'pos': entity_pos,
                                    'distance': distance,
                                    'name': entity_name
                                })
                        except:
                            continue
                except:
                    pass
                
                all_client_data.append(entity_data)
                
            except:
                all_client_data.append(None)  # Add None for failed clients
        
        # Put the data in the queue for the UI thread to process
        self.entity_queue.put(all_client_data)
    
    def update(self):
        """Update the minimap display - call this from the main UI thread"""
        try:
            # Process all queued updates
            while not self.entity_queue.empty():
                all_client_data = self.entity_queue.get_nowait()
                for client_idx, entity_data in enumerate(all_client_data):
                    if entity_data and client_idx < len(self.canvases):
                        self._render_entities(self.canvases[client_idx], entity_data)
            
            # Update minimap positions periodically
            if not hasattr(self, '_position_update_counter'):
                self._position_update_counter = 0
                
            self._position_update_counter += 1
            if self._position_update_counter >= 20:  # Update position every ~1 second
                self._position_update_counter = 0
                self._update_minimap_positions()
                
        except Exception:
            pass
        
        # Schedule the next update
        if self.running and self.windows:
            self.windows[0].after(50, self.update)

    def _render_grid(self, canvas, player_pos, player_orient):
        """Render grid lines on the minimap"""
        # Skip if grid is disabled
        if not self.show_grid:
            canvas.delete("grid")
            return
            
        # Clear previous grid
        canvas.delete("grid")
        
        # Grid configuration
        grid_spacing_game_units = 500  # Distance between grid lines in game units
        grid_color = "#333333"         # Dark gray grid lines
        grid_line_width = 1
        
        # Calculate how many grid lines we need based on radius and grid spacing
        num_lines = math.ceil((self.radius * 2) / grid_spacing_game_units)
        
        # Center of the canvas
        center_x = center_y = self.size / 2
        
        # Calculate rotation matrix for north-oriented map
        if self.north_oriented:
            rotation_angle = -player_orient.yaw
            sin_angle = math.sin(rotation_angle)
            cos_angle = math.cos(rotation_angle)
        else:
            sin_angle = 0
            cos_angle = 1
        
        # Calculate grid origin (nearest grid point to player)
        grid_origin_x = math.floor(player_pos.x / grid_spacing_game_units) * grid_spacing_game_units
        grid_origin_y = math.floor(player_pos.y / grid_spacing_game_units) * grid_spacing_game_units
        
        # Minimap radius in pixels
        minimap_radius = self.size / 2 - 2  # Accounting for border
        
        # Draw vertical grid lines
        for i in range(-num_lines, num_lines + 1):
            # World position of this grid line
            world_x = grid_origin_x + (i * grid_spacing_game_units)
            
            # Calculate start and end points of the line in world coordinates
            start_world_y = player_pos.y - self.radius
            end_world_y = player_pos.y + self.radius
            
            # Calculate relative positions to player
            rel_start_x = world_x - player_pos.x
            rel_start_y = start_world_y - player_pos.y
            rel_end_x = world_x - player_pos.x
            rel_end_y = end_world_y - player_pos.y
            
            # Apply rotation if north-oriented
            if self.north_oriented:
                rot_start_x = rel_start_x * cos_angle - rel_start_y * sin_angle
                rot_start_y = rel_start_x * sin_angle + rel_start_y * cos_angle
                rot_end_x = rel_end_x * cos_angle - rel_end_y * sin_angle
                rot_end_y = rel_end_x * sin_angle + rel_end_y * cos_angle
                rel_start_x, rel_start_y = rot_start_x, rot_start_y
                rel_end_x, rel_end_y = rot_end_x, rot_end_y
            
            # Scale and translate to canvas coordinates
            canvas_start_x = center_x + rel_start_x * self.scale_factor
            canvas_start_y = center_y - rel_start_y * self.scale_factor
            canvas_end_x = center_x + rel_end_x * self.scale_factor
            canvas_end_y = center_y - rel_end_y * self.scale_factor
            
            # Clip line to circle boundary using parametric equation
            # For a line from (x1,y1) to (x2,y2), any point on the line is:
            # (x,y) = (x1,y1) + t*((x2,y2) - (x1,y1)) where 0 <= t <= 1
            
            # Find intersection with circle
            # We need to solve for t where (x-center_x)^2 + (y-center_y)^2 = radius^2
            dx = canvas_end_x - canvas_start_x
            dy = canvas_end_y - canvas_start_y
            
            # Coefficients for quadratic equation
            a = dx*dx + dy*dy
            b = 2 * ((canvas_start_x - center_x) * dx + (canvas_start_y - center_y) * dy)
            c = (canvas_start_x - center_x)**2 + (canvas_start_y - center_y)**2 - minimap_radius**2
            
            # Calculate discriminant
            discriminant = b*b - 4*a*c
            
            # Skip if line doesn't intersect circle
            if discriminant < 0:
                continue
                
            # Calculate intersection points
            t1 = (-b + math.sqrt(discriminant)) / (2*a)
            t2 = (-b - math.sqrt(discriminant)) / (2*a)
            
            # Find valid intersection points (0 <= t <= 1)
            valid_t = []
            if 0 <= t1 <= 1:
                valid_t.append(t1)
            if 0 <= t2 <= 1:
                valid_t.append(t2)
                
            # If both points are outside circle, check if line segment passes through circle
            if not valid_t:
                # Check if start point is inside circle
                start_dist = math.sqrt((canvas_start_x - center_x)**2 + (canvas_start_y - center_y)**2)
                end_dist = math.sqrt((canvas_end_x - center_x)**2 + (canvas_end_y - center_y)**2)
                
                if start_dist <= minimap_radius and end_dist <= minimap_radius:
                    # Both points inside circle, draw full line
                    canvas.create_line(
                        canvas_start_x, canvas_start_y, 
                        canvas_end_x, canvas_end_y,
                        fill=grid_color, width=grid_line_width, tags="grid"
                    )
                # Otherwise, line doesn't intersect circle at all
                continue
                
            # Calculate new endpoints based on intersections
            if len(valid_t) == 2:
                # Line crosses circle twice
                t_min, t_max = min(valid_t), max(valid_t)
                x1 = canvas_start_x + t_min * dx
                y1 = canvas_start_y + t_min * dy
                x2 = canvas_start_x + t_max * dx
                y2 = canvas_start_y + t_max * dy
                
                canvas.create_line(
                    x1, y1, x2, y2,
                    fill=grid_color, width=grid_line_width, tags="grid"
                )
            elif len(valid_t) == 1:
                # Line crosses circle once
                t = valid_t[0]
                x = canvas_start_x + t * dx
                y = canvas_start_y + t * dy
                
                # Check which endpoint is inside the circle
                start_dist = math.sqrt((canvas_start_x - center_x)**2 + (canvas_start_y - center_y)**2)
                
                if start_dist <= minimap_radius:
                    # Start point is inside
                    canvas.create_line(
                        canvas_start_x, canvas_start_y, x, y,
                        fill=grid_color, width=grid_line_width, tags="grid"
                    )
                else:
                    # End point is inside
                    canvas.create_line(
                        x, y, canvas_end_x, canvas_end_y,
                        fill=grid_color, width=grid_line_width, tags="grid"
                    )
        
        # Draw horizontal grid lines using the same approach
        for i in range(-num_lines, num_lines + 1):
            # World position of this grid line
            world_y = grid_origin_y + (i * grid_spacing_game_units)
            
            # Calculate start and end points of the line in world coordinates
            start_world_x = player_pos.x - self.radius
            end_world_x = player_pos.x + self.radius
            
            # Calculate relative positions to player
            rel_start_x = start_world_x - player_pos.x
            rel_start_y = world_y - player_pos.y
            rel_end_x = end_world_x - player_pos.x
            rel_end_y = world_y - player_pos.y
            
            # Apply rotation if north-oriented
            if self.north_oriented:
                rot_start_x = rel_start_x * cos_angle - rel_start_y * sin_angle
                rot_start_y = rel_start_x * sin_angle + rel_start_y * cos_angle
                rot_end_x = rel_end_x * cos_angle - rel_end_y * sin_angle
                rot_end_y = rel_end_x * sin_angle + rel_end_y * cos_angle
                rel_start_x, rel_start_y = rot_start_x, rot_start_y
                rel_end_x, rel_end_y = rot_end_x, rot_end_y
            
            # Scale and translate to canvas coordinates
            canvas_start_x = center_x + rel_start_x * self.scale_factor
            canvas_start_y = center_y - rel_start_y * self.scale_factor
            canvas_end_x = center_x + rel_end_x * self.scale_factor
            canvas_end_y = center_y - rel_end_y * self.scale_factor
            
            # Use the same circle clipping logic as for vertical lines
            dx = canvas_end_x - canvas_start_x
            dy = canvas_end_y - canvas_start_y
            
            # Coefficients for quadratic equation
            a = dx*dx + dy*dy
            b = 2 * ((canvas_start_x - center_x) * dx + (canvas_start_y - center_y) * dy)
            c = (canvas_start_x - center_x)**2 + (canvas_start_y - center_y)**2 - minimap_radius**2
            
            # Calculate discriminant
            discriminant = b*b - 4*a*c
            
            # Skip if line doesn't intersect circle
            if discriminant < 0:
                continue
                
            # Calculate intersection points
            t1 = (-b + math.sqrt(discriminant)) / (2*a)
            t2 = (-b - math.sqrt(discriminant)) / (2*a)
            
            # Find valid intersection points (0 <= t <= 1)
            valid_t = []
            if 0 <= t1 <= 1:
                valid_t.append(t1)
            if 0 <= t2 <= 1:
                valid_t.append(t2)
                
            # If both points are outside circle, check if line segment passes through circle
            if not valid_t:
                # Check if start point is inside circle
                start_dist = math.sqrt((canvas_start_x - center_x)**2 + (canvas_start_y - center_y)**2)
                end_dist = math.sqrt((canvas_end_x - center_x)**2 + (canvas_end_y - center_y)**2)
                
                if start_dist <= minimap_radius and end_dist <= minimap_radius:
                    # Both points inside circle, draw full line
                    canvas.create_line(
                        canvas_start_x, canvas_start_y, 
                        canvas_end_x, canvas_end_y,
                        fill=grid_color, width=grid_line_width, tags="grid"
                    )
                # Otherwise, line doesn't intersect circle at all
                continue
                
            # Calculate new endpoints based on intersections
            if len(valid_t) == 2:
                # Line crosses circle twice
                t_min, t_max = min(valid_t), max(valid_t)
                x1 = canvas_start_x + t_min * dx
                y1 = canvas_start_y + t_min * dy
                x2 = canvas_start_x + t_max * dx
                y2 = canvas_start_y + t_max * dy
                
                canvas.create_line(
                    x1, y1, x2, y2,
                    fill=grid_color, width=grid_line_width, tags="grid"
                )
            elif len(valid_t) == 1:
                # Line crosses circle once
                t = valid_t[0]
                x = canvas_start_x + t * dx
                y = canvas_start_y + t * dy
                
                # Check which endpoint is inside the circle
                start_dist = math.sqrt((canvas_start_x - center_x)**2 + (canvas_start_y - center_y)**2)
                
                if start_dist <= minimap_radius:
                    # Start point is inside
                    canvas.create_line(
                        canvas_start_x, canvas_start_y, x, y,
                        fill=grid_color, width=grid_line_width, tags="grid"
                    )
                else:
                    # End point is inside
                    canvas.create_line(
                        x, y, canvas_end_x, canvas_end_y,
                        fill=grid_color, width=grid_line_width, tags="grid"
                    )

    def _update_zoom_indicator(self):
        """Update the zoom level indicator on all canvases"""
        for canvas in self.canvases:
            # Remove old indicator
            for item in canvas.find_withtag("zoom_indicator"):
                canvas.delete(item)
                
            # Create new indicator
            zoom_percent = int(self.scale_factor * 2000)  # Convert to percentage
            canvas.create_text(
                self.size - 10, 10,
                text=f"Zoom: {zoom_percent}%",
                fill='#AAAAAA',
                font=('Arial', 8),
                anchor='ne',
                tags="zoom_indicator"
            )

    def _update_minimap_positions(self):
        """Update the position of minimap windows to follow client windows"""
        for i, client in enumerate(self.clients):
            if i >= len(self.windows):
                continue
                
            # Skip if manually positioned
            if hasattr(self.windows[i], 'manually_positioned') and self.windows[i].manually_positioned:
                continue
                
            # Skip invalid clients
            if client is None or isinstance(client, int) or not hasattr(client, 'window_handle'):
                continue
            
            try:
                # Get client window position
                if isinstance(client.window_handle, int):
                    rect = win32gui.GetWindowRect(client.window_handle)
                    client_rect = type('Rect', (), {'left': rect[0], 'top': rect[1], 
                                                   'right': rect[2], 'bottom': rect[3]})
                else:
                    client_rect = Window(client.window_handle).rect
                
                # Calculate position for minimap (top-right corner with margin)
                client_width = client_rect.right - client_rect.left
                minimap_x = client_rect.left + client_width - self.size - 20
                minimap_y = client_rect.top + 20
                
                # Update window position
                self.windows[i].geometry(f"+{minimap_x}+{minimap_y}")
                
                # Update zoom indicator to ensure it's visible
                self._update_zoom_indicator()
                
            except Exception:
                pass
    
    def _render_entities(self, canvas, entity_data):
        # Clear previous markers
        canvas.delete("entity")
        canvas.delete("label")
        
        # Initialize entity positions
        if not hasattr(canvas, 'entity_positions'):
            canvas.entity_positions = {}
        else:
            canvas.entity_positions.clear()
        
        # Get player data
        player_pos = entity_data['player']['pos']
        player_orient = entity_data['player']['orient']
        client_idx = self.canvases.index(canvas)
        
        # Render grid if enabled
        if self.show_grid:
            self._render_grid(canvas, player_pos, player_orient)
        
        # Normalize yaw and set center coordinates
        player_orient.yaw = math.radians(math.degrees(player_orient.yaw) % 360)
        center_x = center_y = self.size / 2
        
        # Draw player marker (square with direction indicator)
        square_size = 5
        canvas.create_rectangle(
            center_x - square_size, center_y - square_size, 
            center_x + square_size, center_y + square_size,
            fill='white', outline='black', width=1, tags="entity"
        )
        
        # Draw direction indicator line
        line_length = square_size * 1.5
        direction_x = center_x + line_length * math.sin(player_orient.yaw)
        direction_y = center_y - line_length * math.cos(player_orient.yaw)
        canvas.create_line(
            center_x, center_y, direction_x, direction_y,
            fill='white', width=2, tags="entity"
        )
        
        # Draw North indicator
        compass_radius = self.size / 2 - 15
        north_angle = -player_orient.yaw
        north_x = center_x + compass_radius * math.sin(north_angle)
        north_y = center_y - compass_radius * math.cos(north_angle)
        canvas.create_text(north_x, north_y, text="N", 
                          fill='red', font=('Arial', 10, 'bold'), tags="entity")
        
        # Entity type definitions
        entity_types = {
            'wisp': {'color': 'cyan', 'size': 5},
            'npc': {'color': 'orange', 'size': 7},
            'mob': {'color': 'red', 'size': 7},
            'enemy': {'color': 'red', 'size': 7},
            'player': {'color': 'yellow', 'size': 6},
            'quest': {'color': 'magenta', 'size': 8},
            'sigil': {'color': 'purple', 'size': 8},
            'chest': {'color': 'gold', 'size': 7},
            'collect': {'color': 'gold', 'size': 7},
            'ghost': {'color': '#AAAAAA', 'size': 5},
            'standin': {'color': '#AAAAAA', 'size': 5}
        }
        
        # Draw all other entities
        for entity in entity_data['entities']:
            entity_pos = entity['pos']
            entity_name = entity.get('name', "Unknown")
            name_lower = entity_name.lower()
            
            # Calculate relative position and apply rotation
            rel_x = entity_pos.x - player_pos.x
            rel_y = entity_pos.y - player_pos.y
            
            sin_yaw = math.sin(player_orient.yaw)
            cos_yaw = math.cos(player_orient.yaw)
            
            rotated_x = -(rel_x * cos_yaw - rel_y * sin_yaw)
            rotated_y = -(rel_x * sin_yaw + rel_y * cos_yaw)
            
            # Convert to canvas coordinates
            canvas_x = center_x + (rotated_x * self.scale_factor)
            canvas_y = center_y + (-rotated_y * self.scale_factor)
            
            # Skip if outside minimap bounds
            if math.sqrt((canvas_x - center_x)**2 + (canvas_y - center_y)**2) > (self.size / 2 - 5):
                continue
            
            # Determine entity appearance
            entity_color = 'lime'
            dot_size = 6
            
            # Check for specific entity types
            for key, props in entity_types.items():
                if key in name_lower:
                    entity_color = props['color']
                    dot_size = props['size']
                    break
                    
            # Special handling for wisps
            if 'wisp' in name_lower:
                for wisp_type in ['health', 'mana', 'gold']:
                    if wisp_type in name_lower:
                        entity_name = f"{wisp_type.capitalize()} Wisp"
                        break
            
            # Draw entity dot
            entity_tag = f"entity_{len(canvas.entity_positions)}"
            canvas.create_oval(
                canvas_x - dot_size, canvas_y - dot_size, 
                canvas_x + dot_size, canvas_y + dot_size, 
                fill=entity_color, outline='black', width=1, 
                tags=("entity", entity_tag)
            )
            
            # Store entity data for click handling
            canvas.entity_positions[entity_tag] = {
                'position': entity_pos,
                'name': entity_name,
                'client_idx': client_idx
            }
            
            # Determine if label should be shown
            should_show_label = any(keyword in name_lower for keyword in 
                                   ['wisp', 'quest', 'sigil', 'npc', 'chest'])
            if not should_show_label and 'distance' in entity and entity['distance'] < 1000:
                should_show_label = True
                
            if should_show_label:
                # Truncate long names
                display_name = entity_name[:12] + "..." if len(entity_name) > 15 else entity_name
                label_x = canvas_x + dot_size + 2
                label_y = canvas_y - dot_size - 2
                
                # Draw text with outline
                for offset_x, offset_y in [(-1,-1), (-1,1), (1,-1), (1,1)]:
                    canvas.create_text(
                        label_x + offset_x, label_y + offset_y,
                        text=display_name, fill='black', font=('Arial', 9),
                        anchor='w', tags=("label", entity_tag)
                    )
                
                canvas.create_text(
                    label_x, label_y, text=display_name,
                    fill=entity_color, font=('Arial', 9, 'bold'),
                    anchor='w', tags=("label", entity_tag)
                )
        
        # Bind click event
        if not hasattr(canvas, 'click_bound') or not canvas.click_bound:
            canvas.bind("<Button-1>", lambda event, c=canvas: self._handle_minimap_click(event, c))
            canvas.click_bound = True

    
    def _handle_minimap_click(self, event, canvas):
        """Handle clicks on the minimap to teleport to entities using navmap"""
        if not hasattr(canvas, 'entity_positions'):
            return
            
        # Find the closest entity to the click position
        click_x, click_y = event.x, event.y
        closest_entity = None
        closest_distance = float('inf')
        client_idx = None
        click_radius = 15  # 15px click radius
        
        # Iterate through all entity positions
        for entity_tag, entity_data in canvas.entity_positions.items():
            try:
                coords = canvas.coords(entity_tag)
                if coords:
                    # Calculate center of the oval and distance from click
                    entity_x = (coords[0] + coords[2]) / 2
                    entity_y = (coords[1] + coords[3]) / 2
                    distance = math.sqrt((click_x - entity_x)**2 + (click_y - entity_y)**2)
                    
                    # Update closest entity if this one is closer
                    if distance < closest_distance and distance < click_radius:
                        closest_entity = (entity_data['position'], entity_data['name'])
                        closest_distance = distance
                        client_idx = entity_data['client_idx']
            except:
                continue
                
        # Queue navmap teleport to the closest entity
        if closest_entity and client_idx is not None and client_idx < len(self.clients):
            position, entity_name = closest_entity
            client = self.clients[client_idx]
            
            # Initialize teleport queue if needed
            if not hasattr(self, 'teleport_queue'):
                self.teleport_queue = queue.Queue()
                
            # Add to navmap teleport queue
            self.teleport_queue.put((client, position, entity_name))

    async def start(self):
        """Start the minimap update cycle"""
        if self.running:
            return
        
        # Quick validation checks
        if not self.clients:
            return
        
        # Create windows for each client
        self._create_windows()
        if not self.windows:
            return
        
        # Set running state and start update thread
        self.running = True
        self.update_thread = threading.Thread(target=self._update_loop)
        self.update_thread.daemon = True
        self.update_thread.start()
        
        # Schedule the first update in the main thread
        if self.windows:
            self.windows[0].after(50, self.update)
        else:
            self.running = False
    
    async def stop(self):
        """Stop the minimap and clean up resources"""
        if not self.running:
            return
            
        self.running = False
        
        # Stop the update thread
        if hasattr(self, 'update_thread') and self.update_thread and self.update_thread.is_alive():
            try:
                self.update_thread.join(timeout=1.0)
            except Exception:
                pass
        
        # Clean up windows
        windows_to_destroy = list(self.windows)
        self.windows = []
        self.canvases = []
        
        # Destroy windows safely
        if windows_to_destroy:
            try:
                # Check if tk is still running
                tk_running = False
                try:
                    if tk._default_root and tk._default_root.winfo_exists():
                        tk_running = True
                except:
                    pass
                
                if tk_running:
                    # Create a safer way to destroy windows
                    def destroy_safely():
                        for window in windows_to_destroy:
                            try:
                                if window.winfo_exists():
                                    window.destroy()
                            except:
                                pass
                    
                    # Execute window destruction based on thread context
                    if threading.current_thread() is threading.main_thread():
                        destroy_safely()
                    else:
                        if windows_to_destroy and hasattr(windows_to_destroy[0], 'after_idle'):
                            windows_to_destroy[0].after_idle(destroy_safely)
            except:
                pass
        
        # Clear any remaining items in the queue
        if hasattr(self, 'entity_queue'):
            while not self.entity_queue.empty():
                try:
                    self.entity_queue.get_nowait()
                except:
                    pass
                
        # Clear teleport queue if it exists
        if hasattr(self, 'teleport_queue'):
            while not self.teleport_queue.empty():
                try:
                    self.teleport_queue.get_nowait()
                except:
                    pass