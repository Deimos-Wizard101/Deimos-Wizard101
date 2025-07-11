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

        # Entity icon configuration
        self.use_entity_icons = True  # Toggle for icon usage
        self.entity_icons = {
            'default': {'color': '#FFFFFF', 'shape': 'circle', 'size': 4},
            'player': {'color': '#00FF00', 'shape': 'triangle', 'size': 6},
            'npc': {'color': '#FFFF00', 'shape': 'square', 'size': 5},
            'enemy': {'color': '#FF0000', 'shape': 'diamond', 'size': 5},
            'quest': {'color': '#00FFFF', 'shape': 'star', 'size': 6},
            'wisp': {'color': '#FF00FF', 'shape': 'circle', 'size': 3},
            'chest': {'color': '#FFA500', 'shape': 'square', 'size': 4},
        }
        
        # Entity type classification keywords
        self.entity_type_keywords = {
            'enemy': ['mob', 'enemy', 'monster', 'boss', 'minion'],
            'npc': ['npc', 'vendor', 'merchant', 'quest giver'],
            'quest': ['quest', 'objective', 'goal'],
            'wisp': ['wisp', 'health', 'mana', 'energy'],
            'chest': ['chest', 'container', 'box']
        }

        self.altitude_threshold = 1000.0
    
        # Colors for altitude indicators
        self.above_color = "#00AAFF"  # Light blue for entities above
        self.below_color = "#FF7700"  # Orange for entities below

        # Auto-scaling properties
        self.auto_scale = True
        self.min_scale_factor = 0.005
        self.max_scale_factor = 0.05
        self.density_threshold = 10
        self.last_auto_scale_time = {}  # Dictionary to track per client
        self.client_scale_factors = {}  # Store scale factor per client

        # Animation properties
        self.animation_enabled = True
        self.animation_frames = {}  # Store animation data by canvas and entity ID
        self.animation_speed = 0.05  # Animation update interval in seconds
        self.animation_task = None
        
        # Click feedback animation properties
        self.click_ripple_duration = 0.5  # seconds
        self.click_ripple_max_size = 20  # pixels
        self.click_ripple_color = "#FFFFFF"  # white
        
        # Entity animation properties
        self.pulse_duration = 1.0  # seconds
        self.pulse_scale = 1.3  # maximum scale factor
        self.selection_duration = 0.4  # seconds
        self.teleport_duration = 0.5  # seconds
        
        # Position smoothing properties
        self.position_smoothing = True
        self.smoothing_factor = 0.3  # 0-1, higher = smoother but slower
        self.smooth_positions = {}  # Store smoothed positions by entity
        
        # Fade-in properties
        self.fade_in_duration = 0.5  # seconds
        self.fade_in_steps = 10  # number of opacity steps

        for i, client in enumerate(self.clients):
            client_id = client.process_id if hasattr(client, 'process_id') else i
            self.client_scale_factors[client_id] = self.scale_factor
            self.last_auto_scale_time[client_id] = 0


################# Utilities #################
    def _adjust_color_opacity(self, color, opacity):
        """Adjust color opacity for animations"""
        if color.startswith('#') and len(color) == 7:
            r = int(color[1:3], 16)
            g = int(color[3:5], 16)
            b = int(color[5:7], 16)
            return f"#{r:02x}{g:02x}{b:02x}{opacity:02x}"
        return color

    def _isometric_project(self, x, y, z, player_z):
        """Convert 3D coordinates to 2D isometric view"""
        # Standard isometric projection (30° angles)
        iso_x = (x - y) * 0.866  # cos(30°) ≈ 0.866
        iso_y = (x + y) * 0.5 - (z - player_z) * 0.75  # sin(30°) = 0.5
        return iso_x, iso_y

    def _auto_adjust_scale(self, canvas, entity_count, client_idx):
        """Automatically adjust scale based on entity count and entity clustering"""
        if not hasattr(self, 'auto_scale') or not self.auto_scale:
            return
            
        current_client = self.clients[client_idx] if client_idx < len(self.clients) else None
        client_id = current_client.process_id if hasattr(current_client, 'process_id') else client_idx
        base_scale = self.scale_factor
        current_scale = self.client_scale_factors.get(client_id, base_scale)
        
        current_time = time.time()
        if hasattr(self, 'manual_scale_time') and client_id in self.manual_scale_time:
            time_since_manual = current_time - self.manual_scale_time[client_id]
            if time_since_manual < 10.0:  # 20 seconds cooldown after manual adjustment
                return
        if current_time - self.last_auto_scale_time.get(client_id, 0) < 1.5:  # Reduced cooldown for faster response
            return
        
        if not hasattr(self, 'scale_history'):
            self.scale_history = {}
        if client_id not in self.scale_history:
            self.scale_history[client_id] = [current_scale] * 5
                
        # Calculate scale factor based on entity count
        if entity_count > 30:
            count_scale_factor = 0.4  # More aggressive zoom out for many entities
        elif entity_count > 20:
            count_scale_factor = 0.55 - ((entity_count - 20) / 10) * 0.15
        elif entity_count > 10:
            count_scale_factor = 0.7 - ((entity_count - 10) / 10) * 0.15
        elif entity_count < 3:
            count_scale_factor = 1.8  # More aggressive zoom in for few entities
        else:
            count_scale_factor = 1.8 - ((entity_count - 3) / 7) * 1.1  # Steeper curve
        
        target_scale = base_scale * count_scale_factor
                
        # Adjust for entity clustering
        cluster_detected = False
        if hasattr(canvas, 'entity_positions') and len(canvas.entity_positions) > 3:
            positions = [data['position'] for tag, data in canvas.entity_positions.items()]
            clustering_score = 0
            total_entities = len(positions)
            
            grid_size = 700  # Smaller grid for more precise clustering detection
            spatial_grid = {}
            
            for i, pos in enumerate(positions):
                cell_key = (int(pos.x // grid_size), int(pos.y // grid_size))
                if cell_key not in spatial_grid:
                    spatial_grid[cell_key] = []
                spatial_grid[cell_key].append((i, pos))
            
            # Calculate clustering score
            for i, pos1 in enumerate(positions):
                cell_x, cell_y = int(pos1.x // grid_size), int(pos1.y // grid_size)
                weighted_close = 0
                
                # Check neighboring cells
                for dx in [-1, 0, 1]:
                    for dy in [-1, 0, 1]:
                        cell_key = (cell_x + dx, cell_y + dy)
                        if cell_key in spatial_grid:
                            for j, pos2 in spatial_grid[cell_key]:
                                if i != j:
                                    dist = math.sqrt((pos1.x - pos2.x)**2 + (pos1.y - pos2.y)**2)
                                    threshold = base_threshold = 850
                                    
                                    # Adjust threshold based on current scale
                                    if current_scale < 0.03:
                                        threshold *= 1.4
                                    else:
                                        threshold /= (current_scale / base_scale) * 0.85
                                    
                                    if dist < threshold:
                                        weight = 1.0 - (dist / threshold)**1.6
                                        weighted_close += weight
                
                # Lower threshold for detecting clusters
                if weighted_close > 0.8:
                    cluster_detected = True
                    contribution = 2.2 / (1 + math.exp(-weighted_close + 1.6)) - 1
                    clustering_score += max(0, min(contribution, 1.0))
            
            # Apply clustering adjustments
            if total_entities > 0:
                normalized_score = max(clustering_score / total_entities, 0.05)
                
                if normalized_score > 0.4:
                    cluster_factor = 5.0 * min(normalized_score, 0.95)  # More aggressive zoom for heavy clusters
                    blend_ratio = 0.8 * (1 - math.exp(-normalized_score * 2.5))
                    target_scale = (target_scale * (1 - blend_ratio) + (base_scale * cluster_factor) * blend_ratio)
                elif normalized_score > 0.2:
                    ratio = (normalized_score - 0.2) / 0.2
                    eased_ratio = ratio * (2 - ratio)
                    cluster_factor = 2.5 + (eased_ratio * 2.0)
                    blend_ratio = 0.4 + (eased_ratio * 0.3)
                    target_scale = (target_scale * (1 - blend_ratio) + (base_scale * cluster_factor) * blend_ratio)
                elif normalized_score > 0.1:
                    ratio = (normalized_score - 0.1) / 0.1
                    eased_ratio = ratio * ratio
                    cluster_factor = 2.0 + (eased_ratio * 0.5)
                    blend_ratio = 0.25 + (eased_ratio * 0.15)
                    target_scale = (target_scale * (1 - blend_ratio) + (base_scale * cluster_factor) * blend_ratio)
        
        # Apply smoothing with improved responsiveness
        self.scale_history[client_id].append(target_scale)
        self.scale_history[client_id] = self.scale_history[client_id][-5:]
        
        # More weight on recent values for faster response
        weights = [0.05, 0.1, 0.15, 0.25, 0.45]
        smoothed_target = sum(w * s for w, s in zip(weights, self.scale_history[client_id]))
        
        change_magnitude = abs(smoothed_target - current_scale) / current_scale
        
        # Make zoom-out more responsive than zoom-in
        if smoothed_target < current_scale:  # Zooming out
            alpha = max(0.3, 0.45 - change_magnitude)
        else:  # Zooming in
            alpha = max(0.25, 0.4 - change_magnitude)
            
        # Faster zoom-out when clusters disappear
        if not cluster_detected and current_scale > base_scale * 1.5:
            alpha = min(0.6, alpha * 1.8)
            
        new_scale = current_scale * (1 - alpha) + smoothed_target * alpha
        
        # Apply limits
        max_scale = self.max_scale_factor or 0.18  # Increased max zoom
        min_scale = self.min_scale_factor or 0.004  # Decreased min zoom
        
        new_scale = max(min(new_scale, max_scale), min_scale)
        
        # Update if change is significant - more sensitive for zoom-out
        if smoothed_target < current_scale:  # Zooming out
            adaptive_threshold = 0.03 + (current_scale / max_scale) * 0.02  # Lower threshold for zoom-out
        else:  # Zooming in
            adaptive_threshold = 0.04 + (current_scale / max_scale) * 0.03
            
        relative_change = abs(new_scale - current_scale) / current_scale
        
        if relative_change > adaptive_threshold:
            self.client_scale_factors[client_id] = new_scale
            self.last_auto_scale_time[client_id] = current_time
            
            if hasattr(self, '_update_client_zoom_indicator'):
                self._update_client_zoom_indicator(client_idx)
            elif hasattr(self, '_update_zoom_indicator'):
                self._update_zoom_indicator()

    def _handle_zoom(self, direction, client_idx=None):
        """Handle zoom in/out on the minimap for a specific client or all clients"""
        factor = 1.25 if direction == "in" else 1/1.25
        
        # If client_idx is None, apply to all clients
        if client_idx is None:
            # Find which window triggered the zoom
            focused_window = None
            for i, window in enumerate(self.windows):
                if window.focus_get():
                    focused_window = i
                    break
            
            # If we found a focused window, only zoom that one
            if focused_window is not None:
                client_idx = focused_window
            else:
                # Otherwise update global scale factor
                self.scale_factor = min(max(self.scale_factor * factor, 0.005), 0.12)
                
                # Update all client scales and set manual adjustment time
                current_time = time.time()
                for i, client in enumerate(self.clients):
                    if client is None:
                        continue
                    client_id = client.process_id if hasattr(client, 'process_id') else i
                    current_scale = self.client_scale_factors.get(client_id, self.scale_factor)
                    new_scale = min(max(current_scale * factor, 0.005), 0.12)
                    self.client_scale_factors[client_id] = new_scale
                    
                    # Set manual adjustment time to prevent auto-scaling for 20 seconds
                    if not hasattr(self, 'manual_scale_time'):
                        self.manual_scale_time = {}
                    self.manual_scale_time[client_id] = current_time
                
                self._update_zoom_indicator()
                
                # Force redraw all canvases
                for canvas in self.canvases:
                    if hasattr(canvas, 'entity_positions'):
                        canvas.entity_positions.clear()
                return
        
        # Apply zoom to specific client
        if client_idx < len(self.clients):
            client = self.clients[client_idx]
            client_id = client.process_id if hasattr(client, 'process_id') else client_idx
            current_scale = self.client_scale_factors.get(client_id, self.scale_factor)
            new_scale = min(max(current_scale * factor, 0.005), 0.12)
            self.client_scale_factors[client_id] = new_scale
            
            # Set manual adjustment time to prevent auto-scaling for 20 seconds
            if not hasattr(self, 'manual_scale_time'):
                self.manual_scale_time = {}
            self.manual_scale_time[client_id] = time.time()
            
            # Update zoom indicator for this client
            if client_idx < len(self.windows):
                self._update_client_zoom_indicator(client_idx, new_scale)
            
            # Force redraw this client's canvas
            if client_idx < len(self.canvases):
                canvas = self.canvases[client_idx]
                if hasattr(canvas, 'entity_positions'):
                    canvas.entity_positions.clear()

    def _toggle_grid(self):
        """Toggle grid visibility"""
        self.show_grid = not self.show_grid
        
        # Force redraw all canvases
        for canvas in self.canvases:
            if hasattr(canvas, 'entity_positions'):
                canvas.entity_positions.clear()
    
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
        
        for i, canvas in enumerate(self.canvases):
            if canvas.winfo_id() == window.winfo_id():
                canvas.bind("<ButtonPress-1>", lambda event, c=canvas: self._handle_minimap_click(event, c))

    def _determine_entity_type(self, entity_name):
        """Determine the entity type based on its name"""
        entity_name_lower = entity_name.lower()
        
        for entity_type, keywords in self.entity_type_keywords.items():
            if any(keyword in entity_name_lower for keyword in keywords):
                return entity_type
        
        return 'default'
    
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
                
                try:
                    sprinter = SprintyClient(client)
                    entities = await sprinter.get_base_entity_list()
                    effective_radius = 2000
                    
                    for entity in entities:
                        try:
                            entity_pos = await entity.location()
                            entity_gid = await entity.global_id_full()
                            
                            if entity_gid == player_gid:
                                continue
                                
                            distance = math.sqrt(
                                (entity_pos.x - player_pos.x) ** 2 + 
                                (entity_pos.y - player_pos.y) ** 2
                            )
                            
                            if distance <= effective_radius:
                                entity_name = "Unknown"
                                try:
                                    obj_template = await entity.object_template()
                                    entity_name = await obj_template.object_name()
                                    
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
                all_client_data.append(None)
        
        self.entity_queue.put(all_client_data)

    def _update_client_zoom_indicator(self, client_idx, scale_factor=None):
        """Update the zoom indicator for a specific client"""
        if client_idx >= len(self.windows):
            return
            
        window = self.windows[client_idx]
        
        # If scale_factor is not provided, get it from client_scale_factors
        if scale_factor is None:
            client = self.clients[client_idx] if client_idx < len(self.clients) else None
            client_id = client.process_id if hasattr(client, 'process_id') else client_idx
            scale_factor = self.client_scale_factors.get(client_id, self.scale_factor)
        
        zoom_percentage = int(scale_factor * 100 / 0.05)  # 0.05 is max zoom
        
        if hasattr(window, 'zoom_label'):
            window.zoom_label.config(text=f"Zoom: {zoom_percentage}%")

    def _update_zoom_indicator(self):
        """Update the zoom indicator on all minimaps"""
        for i, window in enumerate(self.windows):
            # Get client-specific scale if available, otherwise use global scale
            current_client = self.clients[i] if i < len(self.clients) else None
            client_id = current_client.process_id if hasattr(current_client, 'process_id') else i
            scale_factor = self.client_scale_factors.get(client_id, self.scale_factor)
            
            zoom_text = f"Zoom: {int(scale_factor * 100 / 0.05)}%"  # 0.05 is max zoom
            
            if not hasattr(window, 'bottom_frame'):
                # Create frame and UI elements
                bottom_frame = tk.Frame(window, bg=self.background_color)
                bottom_frame.place(relx=0.5, rely=1.0, y=-5, anchor='s')
                window.bottom_frame = bottom_frame
                
                # Get client title
                client_title = self.clients[i].title if i < len(self.clients) and hasattr(self.clients[i], 'title') else f'Client {i+1}'
                
                # Create labels
                window.title_label = tk.Label(bottom_frame, text=client_title, fg=self.border_color, 
                                            bg=self.background_color, font=('Arial', 14, 'bold'))
                window.title_label.pack(side=tk.LEFT, padx=3)
                
                tk.Label(bottom_frame, text="|", fg=self.border_color, 
                        bg=self.background_color, font=('Arial', 14)).pack(side=tk.LEFT, padx=3)
                
                window.zoom_label = tk.Label(bottom_frame, text=zoom_text, fg=self.border_color, 
                                        bg=self.background_color, font=('Arial', 14))
                window.zoom_label.pack(side=tk.LEFT, padx=3)
            elif hasattr(window, 'zoom_label'):
                window.zoom_label.config(text=zoom_text)

    def _handle_minimap_click(self, event, canvas):
        """Handle clicks on the minimap to teleport to entities"""
        if not hasattr(canvas, 'entity_positions'):
            return
            
        click_x, click_y = event.x, event.y
        # Reduce click radius for more precise detection
        click_radius = 5  # Reduced from 15 to 5
        closest_entity = None
        client_idx = None
        
        # Add click ripple animation
        self._add_click_ripple_animation(canvas, click_x, click_y)
        
        # Get items exactly at click position first for direct hits
        clicked_items = canvas.find_overlapping(
            click_x, click_y, click_x, click_y
        )
        
        # If no direct hits, use a very small radius
        if not clicked_items:
            clicked_items = canvas.find_overlapping(
                click_x-click_radius, click_y-click_radius, 
                click_x+click_radius, click_y+click_radius
            )
        
        potential_matches = []
        
        # Process clicked items
        for item in clicked_items:
            for tag in canvas.gettags(item):
                if tag.startswith("entity_") and tag in canvas.entity_positions:
                    entity_data = canvas.entity_positions[tag]
                    coords = canvas.coords(item)
                    
                    if not coords:
                        continue
                        
                    try:
                        # Calculate center based on shape type
                        if len(coords) >= 4:  # Rectangle or oval
                            entity_x, entity_y = (coords[0] + coords[2]) / 2, (coords[1] + coords[3]) / 2
                        elif len(coords) == 2:  # Point
                            entity_x, entity_y = coords[0], coords[1]
                        else:  # Polygon
                            entity_x = sum(coords[0::2]) / (len(coords) // 2) if coords else click_x
                            entity_y = sum(coords[1::2]) / (len(coords) // 2) if len(coords) > 1 else click_y
                        
                        # For polygons, check if the click is inside the polygon
                        if len(coords) > 4:  # It's a polygon
                            if not self._point_in_polygon(click_x, click_y, coords):
                                continue
                        
                        distance = math.sqrt((click_x - entity_x)**2 + (click_y - entity_y)**2)
                        
                        # Only consider very close matches
                        if distance <= click_radius:
                            potential_matches.append({
                                'entity': (entity_data['position'], entity_data['name']),
                                'distance': distance,
                                'client_idx': entity_data['client_idx'],
                                'coords': coords,
                                'entity_x': entity_x,
                                'entity_y': entity_y,
                                'tag': tag,
                                'item': item
                            })
                    except (IndexError, ZeroDivisionError):
                        continue
        
        # Find closest match
        if potential_matches:
            closest_match = min(potential_matches, key=lambda x: x['distance'])
            closest_entity = closest_match['entity']
            client_idx = closest_match['client_idx']
            
            # Add selection animation for the clicked entity
            entity_x = closest_match['entity_x']
            entity_y = closest_match['entity_y']
            coords = closest_match['coords']
            
            # Calculate entity size for animation
            if len(coords) >= 4:  # Rectangle or oval
                entity_size = max((coords[2] - coords[0]) / 2, (coords[3] - coords[1]) / 2)
            else:
                entity_size = 5  # Default size for points or polygons
            
            # Add selection and teleport animations
            self._add_selection_animation(canvas, entity_x, entity_y, entity_size, closest_match['tag'])
            self._add_teleport_animation(canvas, entity_x, entity_y, entity_size, closest_match['tag'])
        
        # Queue teleport if entity found
        if closest_entity and client_idx is not None and client_idx < len(self.clients):
            position, entity_name = closest_entity
            client = self.clients[client_idx]
            
            if not hasattr(self, 'teleport_queue'):
                self.teleport_queue = queue.Queue()
                    
            self.teleport_queue.put((client, position, entity_name))
    
    def _point_in_polygon(self, x, y, polygon_coords):
        """Check if a point is inside a polygon using ray casting algorithm"""
        # Convert flat list to points
        points = []
        for i in range(0, len(polygon_coords), 2):
            if i+1 < len(polygon_coords):
                points.append((polygon_coords[i], polygon_coords[i+1]))
        
        if len(points) < 3:
            return False
        
        # Ray casting algorithm
        inside = False
        j = len(points) - 1
        
        for i in range(len(points)):
            xi, yi = points[i]
            xj, yj = points[j]
            
            intersect = ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi)
            if intersect:
                inside = not inside
            j = i
        
        return inside
    
################# Animation Stuff #################
    def _add_teleport_animation(self, canvas, entity_x, entity_y, entity_size, tag):
        """Create a teleport animation effect"""
        # Create a flash effect
        flash_radius = entity_size * 1.2
        flash = canvas.create_oval(
            entity_x - flash_radius, entity_y - flash_radius,
            entity_x + flash_radius, entity_y + flash_radius,
            fill='white', outline='', tags=f"teleport_{tag}"
        )
        
        # Animate the flash
        duration = 300  # milliseconds
        steps = 10
        step_time = duration / steps
        
        def animate_teleport(step=0):
            if step >= steps or not self.running:
                canvas.delete(flash)
                return
            
            # Flash animation - fade out
            opacity = int(255 * (1 - step / steps))
            color = f'#{opacity:02x}{opacity:02x}{opacity:02x}'
            canvas.itemconfig(flash, fill=color)
            
            # Schedule next animation frame
            if canvas.winfo_exists():
                canvas.after(int(step_time), lambda: animate_teleport(step + 1))
        
        # Start animation
        animate_teleport()

    def _add_click_ripple_animation(self, canvas, x, y):
        """Create a ripple animation at the click location"""
        # Initial ripple size
        radius = 5
        max_radius = 20
        duration = 300  # milliseconds
        steps = 10
        step_time = duration / steps
        
        # Create the initial ripple
        ripple = canvas.create_oval(
            x - radius, y - radius, 
            x + radius, y + radius, 
            outline='white', width=2, tags="animation"
        )
        
        # Animate the ripple expanding
        def animate_ripple(step=0):
            nonlocal radius
            if step >= steps or not self.running:
                canvas.delete(ripple)
                return
                
            # Increase radius and decrease opacity
            radius += (max_radius - 5) / steps
            opacity = int(255 * (1 - step / steps))
            color = f'#{opacity:02x}{opacity:02x}{opacity:02x}'
            
            canvas.itemconfig(ripple, outline=color)
            canvas.coords(ripple, x - radius, y - radius, x + radius, y + radius)
            
            # Schedule next animation frame
            if canvas.winfo_exists():
                canvas.after(int(step_time), lambda: animate_ripple(step + 1))
        
        # Start animation
        animate_ripple()

    def _add_selection_animation(self, canvas, entity_x, entity_y, entity_size, tag):
        """Create a selection animation around the clicked entity"""
        # Create a pulsing highlight effect
        highlight_size = entity_size * 1.5
        highlight = canvas.create_oval(
            entity_x - highlight_size, entity_y - highlight_size,
            entity_x + highlight_size, entity_y + highlight_size,
            outline='yellow', width=2, tags=f"selection_{tag}"
        )
        
        # Animate the highlight
        duration = 500  # milliseconds
        steps = 15
        step_time = duration / steps
        
        def animate_selection(step=0):
            if step >= steps or not self.running:
                canvas.delete(highlight)
                return
            
            # Pulsing effect - size and opacity
            pulse_factor = 1 + 0.2 * math.sin(step * math.pi / (steps/2))
            current_size = highlight_size * pulse_factor
            
            # Update highlight size
            canvas.coords(
                highlight,
                entity_x - current_size, entity_y - current_size,
                entity_x + current_size, entity_y + current_size
            )
            
            # Update opacity
            opacity = int(200 * (1 - step / steps))
            color = f'#{255:02x}{255:02x}{opacity:02x}'  # Yellow with fading opacity
            canvas.itemconfig(highlight, outline=color)
            
            # Schedule next animation frame
            if canvas.winfo_exists():
                canvas.after(int(step_time), lambda: animate_selection(step + 1))
        
        # Start animation
        animate_selection()

################ Window Creation ####################
    def _create_windows(self):
        """Create minimap windows for each client"""
        # Clear existing windows
        for window in self.windows:
            try:
                window.destroy()
            except Exception:
                pass
        
        self.windows = []
        self.canvases = []
        
        # Create a window for each client
        for i, client in enumerate(self.clients):
            if client is None or isinstance(client, int) or not hasattr(client, 'title'):
                self._create_fallback_window(i, client)
                continue
            
            try:
                # Create window with transparent background
                root = tk.Toplevel()
                root.title("")
                root.geometry(f"{self.size}x{self.size + 30}+{20 + i*50}+{20 + i*50}")
                root.attributes('-topmost', True, '-alpha', 0.85)
                root.configure(bg=self.background_color)
                root.overrideredirect(True)
                root.wm_attributes('-transparentcolor', self.background_color)
                
                # Create frame and canvas
                frame = tk.Frame(root, bg=self.background_color)
                frame.pack(fill=tk.BOTH, expand=True)
                
                canvas = tk.Canvas(frame, width=self.size, height=self.size, 
                                  bg=self.background_color, highlightthickness=0)
                canvas.pack(fill=tk.BOTH, expand=False)
                
                # Create circular minimap
                canvas.create_oval(2, 2, self.size-2, self.size-2, 
                                  fill=self.inner_color, outline='', 
                                  tags="background", stipple='gray12')
                canvas.create_oval(2, 2, self.size-2, self.size-2, 
                                  outline=self.border_color, width=2, tags="border")
                
                self._add_drag_functionality(root)
                self.windows.append(root)
                self.canvases.append(canvas)
        
                # Bind key controls with client index
                root.bind("+", lambda event, idx=i: self._handle_zoom("in", idx))
                root.bind("-", lambda event, idx=i: self._handle_zoom("out", idx))
                root.bind("=", lambda event, idx=i: self._handle_zoom("in", idx))
                root.bind("g", lambda event: self._toggle_grid())
                
            except Exception:
                self._create_fallback_window(i, client)
                
        self._update_zoom_indicator()

    def _create_fallback_window(self, i, client):
        """Create a fallback window if we can't get the client window position"""
        root = tk.Toplevel()
        root.title("")
        root.geometry(f"{self.size}x{self.size + 30}+{20 + i*50}+{20 + i*50}")
        root.attributes('-topmost', True, '-alpha', 0.85)
        root.configure(bg=self.background_color)
        root.overrideredirect(True)
        root.wm_attributes('-transparentcolor', self.background_color)
        
        # Create frame and canvas
        frame = tk.Frame(root, bg=self.background_color)
        frame.pack(fill=tk.BOTH, expand=True)
        
        canvas = tk.Canvas(frame, width=self.size, height=self.size, 
                          bg=self.background_color, highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=False)
        
        # Create circular minimap
        canvas.create_oval(2, 2, self.size-2, self.size-2, 
                          fill=self.inner_color, outline='', tags="background", stipple='gray12')
        canvas.create_oval(2, 2, self.size-2, self.size-2, 
                          outline=self.border_color, width=2, tags="border")
        
        self._add_drag_functionality(root)
        self.windows.append(root)
        self.canvases.append(canvas)
        
        # Bind key controls with client index
        root.bind("+", lambda event, idx=i: self._handle_zoom("in", idx))
        root.bind("-", lambda event, idx=i: self._handle_zoom("out", idx))
        root.bind("=", lambda event, idx=i: self._handle_zoom("in", idx))
        root.bind("g", lambda event: self._toggle_grid())
    

############### Update Stuff ####################
    def _update_click_ripple(self, canvas, anim_data, progress):
        """Update click ripple animation"""
        size = self.click_ripple_max_size * progress
        opacity = int(255 * (1 - progress))
        color = self._adjust_color_opacity(self.click_ripple_color, opacity)
        
        x, y = anim_data['x'], anim_data['y']
        canvas.delete(anim_data['item_id'])
        anim_data['item_id'] = canvas.create_oval(
            x - size, y - size, 
            x + size, y + size, 
            outline=color, width=2, fill=""
        )

    def _update_pulse_animation(self, canvas, anim_data, progress):
        """Update entity pulse animation"""
        entity_id = anim_data['entity_id']
        if entity_id not in canvas.entity_positions:
            return
            
        entity_data = canvas.entity_positions[entity_id]
        
        # Calculate pulse scale using sine wave for smooth pulsing
        pulse_factor = 1 + (self.pulse_scale - 1) * abs(math.sin(progress * math.pi))
        
        # Get entity type and base size
        entity_type = entity_data.get('type', 'default')
        base_size = self.entity_icons[entity_type]['size']
        
        # Apply pulse to size
        pulsed_size = base_size * pulse_factor
        
        # Store original size and redraw with new size
        original_size = self.entity_icons[entity_type]['size']
        self.entity_icons[entity_type]['size'] = pulsed_size
        self._draw_entity(canvas, entity_id, entity_data)
        self.entity_icons[entity_type]['size'] = original_size

    def _update_selection_animation(self, canvas, anim_data, progress):
        """Update selection animation"""
        size = anim_data['max_size'] * progress
        opacity = int(255 * (1 - progress))
        color = self._adjust_color_opacity(anim_data['color'], opacity)
        
        x, y = anim_data['x'], anim_data['y']
        canvas.delete(anim_data['item_id'])
        anim_data['item_id'] = canvas.create_oval(
            x - size, y - size, 
            x + size, y + size, 
            outline=color, width=2, fill=""
        )

    def _update_teleport_animation(self, canvas, anim_data, progress):
        """Update teleport animation"""
        entity_id = anim_data['entity_id']
        if entity_id not in canvas.entity_positions:
            return
            
        # Shrinking effect
        scale = 1 - (progress * 0.8)
        opacity = int(255 * (1 - progress))
        
        x, y = anim_data['x'], anim_data['y']
        size = anim_data['size'] * scale
        color = self._adjust_color_opacity(anim_data['color'], opacity)
        
        canvas.delete(anim_data['item_id'])
        
        # Create shrinking circle
        anim_data['item_id'] = canvas.create_oval(
            x - size, y - size, 
            x + size, y + size, 
            fill=color, outline=""
        )
        
        # Add sparkle effect
        if progress > 0.5:
            sparkle_progress = (progress - 0.5) * 2
            sparkle_size = size * 0.5
            sparkle_count = 6
            
            for i in range(sparkle_count):
                angle = (i / sparkle_count) * 2 * math.pi
                distance = sparkle_size * 2 * sparkle_progress
                sx = x + math.cos(angle) * distance
                sy = y + math.sin(angle) * distance
                
                canvas.create_oval(
                    sx - sparkle_size/4, sy - sparkle_size/4,
                    sx + sparkle_size/4, sy + sparkle_size/4,
                    fill=color, outline=""
                )

    async def _animation_loop(self):
        """Process all active animations"""
        while self.running and self.animation_enabled:
            for canvas_idx, canvas in enumerate(self.canvases):
                if not hasattr(canvas, 'animations'):
                    canvas.animations = {}
                
                # Process each animation
                to_remove = []
                for anim_id, anim_data in canvas.animations.items():
                    anim_type = anim_data['type']
                    progress = (time.time() - anim_data['start_time']) / anim_data['duration']
                    
                    if progress >= 1.0:
                        # Animation complete
                        if anim_type == 'click_ripple':
                            canvas.delete(anim_data['item_id'])
                        elif anim_type == 'pulse':
                            # Reset entity to original size
                            if 'entity_id' in anim_data and anim_data['entity_id'] in canvas.entity_positions:
                                self._draw_entity(canvas, anim_data['entity_id'], canvas.entity_positions[anim_data['entity_id']])
                        elif anim_type == 'selection':
                            canvas.delete(anim_data['item_id'])
                        elif anim_type == 'teleport':
                            canvas.delete(anim_data['item_id'])
                            
                        to_remove.append(anim_id)
                    else:
                        # Update animation
                        if anim_type == 'click_ripple':
                            self._update_click_ripple(canvas, anim_data, progress)
                        elif anim_type == 'pulse':
                            self._update_pulse_animation(canvas, anim_data, progress)
                        elif anim_type == 'selection':
                            self._update_selection_animation(canvas, anim_data, progress)
                        elif anim_type == 'teleport':
                            self._update_teleport_animation(canvas, anim_data, progress)
                
                # Remove completed animations
                for anim_id in to_remove:
                    if anim_id in canvas.animations:
                        del canvas.animations[anim_id]
            
            await asyncio.sleep(self.animation_speed)

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
                                if client in active_teleport_tasks and not active_teleport_tasks[client].done():
                                    active_teleport_tasks[client].cancel()
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
            for task in active_teleport_tasks.values():
                if not task.done():
                    task.cancel()
            
            try:
                loop.close()
            except:
                pass

    def update(self):
        """Update the minimap display - call this from the main UI thread"""
        try:
            # Process all queued updates
            while not self.entity_queue.empty():
                all_client_data = self.entity_queue.get_nowait()
                for client_idx, entity_data in enumerate(all_client_data):
                    if entity_data and client_idx < len(self.canvases):
                        self._render_entities(self.canvases[client_idx], entity_data)
            
            # Update minimap positions every ~1 second
            if not hasattr(self, '_position_update_counter'):
                self._position_update_counter = 0
                
            self._position_update_counter += 1
            if self._position_update_counter >= 20:
                self._position_update_counter = 0
                self._update_minimap_positions()
                
        except Exception:
            pass
        
        # Schedule the next update
        if self.running and self.windows:
            self.windows[0].after(50, self.update)

    def _update_minimap_positions(self):
        """Update the position of minimap windows to follow client windows"""
        for i, client in enumerate(self.clients):
            if (i >= len(self.windows) or 
                (hasattr(self.windows[i], 'manually_positioned') and self.windows[i].manually_positioned) or
                client is None or isinstance(client, int) or not hasattr(client, 'window_handle')):
                continue
            
            try:
                # Get client window position
                if isinstance(client.window_handle, int):
                    rect = win32gui.GetWindowRect(client.window_handle)
                    client_rect = type('Rect', (), {'left': rect[0], 'top': rect[1], 
                                                   'right': rect[2], 'bottom': rect[3]})
                else:
                    client_rect = Window(client.window_handle).rect
                
                # Position minimap in top-right corner with margin
                client_width = client_rect.right - client_rect.left
                self.windows[i].geometry(f"+{client_rect.left + client_width - self.size - 20}+{client_rect.top + 20}")
                
                self._update_zoom_indicator()
            except Exception:
                pass

############## Rendering ######################
    def _render_grid(self, canvas, player_pos, player_orient):
        """Render grid lines on the minimap"""
        if not self.show_grid:
            canvas.delete("grid")
            return
            
        canvas.delete("grid")
        
        grid_spacing = 500  # Game units between grid lines
        grid_color = "#333333"
        grid_line_width = 1
        
        num_lines = math.ceil((self.radius * 2) / grid_spacing)
        center_x = center_y = self.size / 2
        minimap_radius = self.size / 2 - 2
        
        # Calculate rotation for north-oriented map
        if self.north_oriented:
            rotation_angle = -player_orient.yaw
            sin_angle = math.sin(rotation_angle)
            cos_angle = math.cos(rotation_angle)
        else:
            sin_angle = 0
            cos_angle = 1
        
        # Find grid origin (nearest grid point to player)
        grid_origin_x = math.floor(player_pos.x / grid_spacing) * grid_spacing
        grid_origin_y = math.floor(player_pos.y / grid_spacing) * grid_spacing
        
        # Helper function to draw a grid line
        def draw_grid_line(start_x, start_y, end_x, end_y):
            # Calculate relative positions to player
            rel_start_x = start_x - player_pos.x
            rel_start_y = start_y - player_pos.y
            rel_end_x = end_x - player_pos.x
            rel_end_y = end_y - player_pos.y
            
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
            
            # Find intersection with circle
            dx = canvas_end_x - canvas_start_x
            dy = canvas_end_y - canvas_start_y
            
            # Coefficients for quadratic equation
            a = dx*dx + dy*dy
            b = 2 * ((canvas_start_x - center_x) * dx + (canvas_start_y - center_y) * dy)
            c = (canvas_start_x - center_x)**2 + (canvas_start_y - center_y)**2 - minimap_radius**2
            
            # Calculate discriminant
            discriminant = b*b - 4*a*c
            if discriminant < 0:
                return
                
            # Calculate intersection points
            t1 = (-b + math.sqrt(discriminant)) / (2*a)
            t2 = (-b - math.sqrt(discriminant)) / (2*a)
            
            # Find valid intersection points
            valid_t = [t for t in [t1, t2] if 0 <= t <= 1]
            
            if not valid_t:
                # Check if both points are inside circle
                start_dist = math.sqrt((canvas_start_x - center_x)**2 + (canvas_start_y - center_y)**2)
                end_dist = math.sqrt((canvas_end_x - center_x)**2 + (canvas_end_y - center_y)**2)
                
                if start_dist <= minimap_radius and end_dist <= minimap_radius:
                    canvas.create_line(
                        canvas_start_x, canvas_start_y, 
                        canvas_end_x, canvas_end_y,
                        fill=grid_color, width=grid_line_width, tags="grid"
                    )
                return
                
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
                    canvas.create_line(
                        canvas_start_x, canvas_start_y, x, y,
                        fill=grid_color, width=grid_line_width, tags="grid"
                    )
                else:
                    canvas.create_line(
                        x, y, canvas_end_x, canvas_end_y,
                        fill=grid_color, width=grid_line_width, tags="grid"
                    )
        
        # Draw vertical grid lines
        for i in range(-num_lines, num_lines + 1):
            world_x = grid_origin_x + (i * grid_spacing)
            draw_grid_line(
                world_x, player_pos.y - self.radius,
                world_x, player_pos.y + self.radius
            )
        
        # Draw horizontal grid lines
        for i in range(-num_lines, num_lines + 1):
            world_y = grid_origin_y + (i * grid_spacing)
            draw_grid_line(
                player_pos.x - self.radius, world_y,
                player_pos.x + self.radius, world_y
            )

################ Screen Drawing #####################
    def _draw_entity_icon(self, canvas, x, y, entity_type, tag=None, altitude_diff=None):
        """Draw an entity icon on the canvas based on its type"""
        icon_config = self.entity_icons.get(entity_type, self.entity_icons['default'])
        color = icon_config['color']
        shape = icon_config['shape']
        size = icon_config['size'] * 1.3
        
        # Draw altitude indicator if needed
        if altitude_diff is not None and abs(altitude_diff) > self.altitude_threshold:
            indicator_y = y - size - 8
            indicator_text = "▲" if altitude_diff > self.altitude_threshold else "▼"
            indicator_color = self.above_color if altitude_diff > self.altitude_threshold else self.below_color
            canvas.create_text(x, indicator_y, text=indicator_text, fill=indicator_color, 
                              font=('Arial', 12, 'bold'), tags=tag)
        
        # Override color and shape for entities on different floors
        if altitude_diff is not None and abs(altitude_diff) > self.altitude_threshold:
            color = self.above_color if altitude_diff > self.altitude_threshold else self.below_color
            if shape == 'triangle':
                points = [
                    x, y - size if altitude_diff > self.altitude_threshold else y + size,  # Top/Bottom point
                    x - size, y + size if altitude_diff > self.altitude_threshold else y - size,  # Left
                    x + size, y + size if altitude_diff > self.altitude_threshold else y - size   # Right
                ]
                return canvas.create_polygon(points, fill=color, outline='', tags=tag)
        
        # Create shape based on configuration
        if shape == 'circle':
            return canvas.create_oval(x - size, y - size, x + size, y + size, 
                                     fill=color, outline='', tags=tag)
        elif shape == 'square':
            return canvas.create_rectangle(x - size, y - size, x + size, y + size, 
                                          fill=color, outline='', tags=tag)
        elif shape == 'triangle':
            points = [x, y - size, x - size, y + size, x + size, y + size]
            return canvas.create_polygon(points, fill=color, outline='', tags=tag)
        elif shape == 'diamond':
            points = [x, y - size, x + size, y, x, y + size, x - size, y]
            return canvas.create_polygon(points, fill=color, outline='', tags=tag)
        elif shape == 'star':
            outer_radius, inner_radius = size, size / 2.5
            points = []
            for i in range(10):
                radius = outer_radius if i % 2 == 0 else inner_radius
                angle = math.pi / 5 * i
                points.append(x + radius * math.sin(angle))
                points.append(y - radius * math.cos(angle))
            return canvas.create_polygon(points, fill=color, outline='', tags=tag)
        else:
            return canvas.create_oval(x - size, y - size, x + size, y + size, 
                                     fill=color, outline='', tags=tag)

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

        visible_entity_count = len(entity_data['entities'])
        current_client = self.clients[client_idx] if client_idx < len(self.clients) else None
        client_id = current_client.process_id if hasattr(current_client, 'process_id') else client_idx

        
        # Render grid if enabled
        if self.show_grid:
            self._render_grid(canvas, player_pos, player_orient)
        
        # Normalize yaw and set center coordinates
        player_orient.yaw = math.radians(math.degrees(player_orient.yaw) % 360)
        center_x = center_y = self.size / 2
        
        # Draw player marker with custom icon
        if self.use_entity_icons:
            self._draw_entity_icon(canvas, center_x, center_y, 'player', "entity")
            
            # Draw direction indicator line
            line_length = 8  # Slightly longer than the player icon
            direction_x = center_x + line_length * math.sin(player_orient.yaw)
            direction_y = center_y - line_length * math.cos(player_orient.yaw)
            canvas.create_line(
                center_x, center_y, direction_x, direction_y,
                fill='white', width=2, tags="entity"
            )
        else:
            # Draw traditional player marker (square with direction indicator)
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
        
        # Entity type definitions (used when not using icons)
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
        
        sorted_entities = sorted(entity_data['entities'], 
                                key=lambda e: (e['pos'].x - player_pos.x)**2 + 
                                            (e['pos'].y - player_pos.y)**2 + 
                                            (e['pos'].z - player_pos.z)**2)
        
        # Track label positions to prevent overlap
        label_positions = {}
        entities_with_labels = []

        # Draw all other entities
        for entity in sorted_entities:
            entity_pos = entity['pos']
            entity_name = entity.get('name', "Unknown")
            name_lower = entity_name.lower()
            
            # Calculate altitude difference between player and entity
            altitude_diff = entity_pos.z - player_pos.z
            
            # Calculate relative position and apply rotation
            rel_x = entity_pos.x - player_pos.x
            rel_y = entity_pos.y - player_pos.y
            
            sin_yaw = math.sin(player_orient.yaw)
            cos_yaw = math.cos(player_orient.yaw)
            
            rotated_x = -(rel_x * cos_yaw - rel_y * sin_yaw)
            rotated_y = -(rel_x * sin_yaw + rel_y * cos_yaw)
            
            # Get scale factor for this specific client - use the stored value
            client_scale = self.client_scale_factors.get(client_id, self.scale_factor)
            canvas_x = center_x + (rotated_x * client_scale)
            canvas_y = center_y + (-rotated_y * client_scale)
            
            # Skip if outside minimap bounds
            if math.sqrt((canvas_x - center_x)**2 + (canvas_y - center_y)**2) > (self.size / 2 - 5):
                continue
            
            # Create entity tag for identification
            entity_tag = f"entity_{len(canvas.entity_positions)}"
            
            # Store entity data for click handling
            canvas.entity_positions[entity_tag] = {
                'position': entity_pos,
                'name': entity_name,
                'client_idx': client_idx,
                'altitude_diff': altitude_diff  # Store altitude difference
            }
            
            # Special handling for wisps
            if 'wisp' in name_lower:
                for wisp_type in ['health', 'mana', 'gold']:
                    if wisp_type in name_lower:
                        entity_name = f"{wisp_type.capitalize()} Wisp"
                        break
            
            # Draw entity using either icons or traditional dots
            if self.use_entity_icons:
                # Determine entity type based on name
                entity_type = 'default'
                
                # Check for specific entity types in name
                if any(key in name_lower for key in ['mob', 'enemy', 'boss', 'minion']):
                    entity_type = 'enemy'
                elif any(key in name_lower for key in ['npc', 'vendor', 'merchant']):
                    entity_type = 'npc'
                elif any(key in name_lower for key in ['quest', 'objective']):
                    entity_type = 'quest'
                elif 'wisp' in name_lower:
                    entity_type = 'wisp'
                elif any(key in name_lower for key in ['chest', 'container']):
                    entity_type = 'chest'
                elif 'sigil' in name_lower:
                    entity_type = 'quest'  # Use quest icon for sigils
                
                # Override entity type based on altitude - only if difference is significant
                if abs(altitude_diff) > self.altitude_threshold:
                    if altitude_diff > self.altitude_threshold:
                        entity_type = 'above'
                    else:
                        entity_type = 'below'
                
                # Draw the appropriate icon
                self._draw_entity_icon(canvas, canvas_x, canvas_y, entity_type, ("entity", entity_tag), altitude_diff)
            else:
                # Traditional dot rendering with altitude colors
                entity_color = 'lime'
                dot_size = 6
                
                # Check for specific entity types
                for key, props in entity_types.items():
                    if key in name_lower:
                        entity_color = props['color']
                        dot_size = props['size']
                        break
                
                # Override color if entity is on a different floor
                if abs(altitude_diff) > self.altitude_threshold:
                    if altitude_diff > self.altitude_threshold:
                        entity_color = self.above_color  # Entity is above player
                    elif altitude_diff < -self.altitude_threshold:
                        entity_color = self.below_color  # Entity is below player
                
                # Draw entity dot
                canvas.create_oval(
                    canvas_x - dot_size, canvas_y - dot_size, 
                    canvas_x + dot_size, canvas_y + dot_size, 
                    fill=entity_color, outline='black', width=1, 
                    tags=("entity", entity_tag)
                )
            
            # Determine if label should be shown
            should_show_label = any(keyword in name_lower for keyword in 
                                ['wisp', 'quest', 'sigil', 'npc', 'chest'])
            if not should_show_label and 'distance' in entity and entity['distance'] < 1300:
                should_show_label = True
                
            if should_show_label:
                # Store this entity for label processing
                entities_with_labels.append({
                    'x': canvas_x,
                    'y': canvas_y,
                    'name': entity_name,
                    'altitude_diff': altitude_diff,
                    'tag': entity_tag,
                    'distance': (entity_pos.x - player_pos.x)**2 + 
                               (entity_pos.y - player_pos.y)**2 + 
                               (entity_pos.z - player_pos.z)**2
                })
                
            for label_info in sorted(entities_with_labels, key=lambda e: e['distance']):
                canvas_x = label_info['x']
                canvas_y = label_info['y']
                entity_name = label_info['name']
                altitude_diff = label_info['altitude_diff']
                entity_tag = label_info['tag']
                
                # Truncate long names
                display_name = entity_name[:12] + "..." if len(entity_name) > 15 else entity_name
                
                # Determine label color based on altitude
                label_color = 'white'
                if abs(altitude_diff) > self.altitude_threshold:
                    if altitude_diff > self.altitude_threshold:
                        label_color = self.above_color
                    elif altitude_diff < -self.altitude_threshold:
                        label_color = self.below_color
                
                # Calculate label position
                label_x = canvas_x
                label_y = canvas_y + 15
                
                # Check for label overlap
                label_key = f"{int(label_x/10)},{int(label_y/10)}"
                if label_key in label_positions:
                    continue  # Skip this label as it would overlap
                
                # Mark this position as occupied
                label_positions[label_key] = True
                
                # Draw text with outline for better visibility
                for offset_x, offset_y in [(-1,-1), (-1,1), (1,-1), (1,1)]:
                    canvas.create_text(
                        label_x + offset_x, label_y + offset_y,
                        text=display_name, fill='black', font=('Arial', 9),
                        anchor='center', tags=("label", entity_tag)
                    )
                
                # Draw the actual label text
                canvas.create_text(
                    label_x, label_y,
                    text=display_name,
                    fill=label_color,
                    font=('Arial', 9, 'bold'),
                    tags=("label", entity_tag),
                    anchor='center'
                )
                
                # Position label based on icon or dot size
                #dot_size = 6  # Default size
                #if self.use_entity_icons:
                #    dot_size = self.entity_icons.get(entity_type, self.entity_icons['default'])['size']
                #else:
                #    for key, props in entity_types.items():
                #        if key in name_lower:
                #            dot_size = props['size']
                #            break
                
                #label_x = canvas_x + dot_size + 2
                #label_y = canvas_y - dot_size - 2
                
                # Draw text with outline
                #for offset_x, offset_y in [(-1,-1), (-1,1), (1,-1), (1,1)]:
                #    canvas.create_text(
                #        label_x + offset_x, label_y + offset_y,
                #        text=display_name, fill='black', font=('Arial', 9),
                #        anchor='w', tags=("label", entity_tag)
                #    )
        
        visible_entity_count = len(entity_data['entities'])
        self._auto_adjust_scale(canvas, visible_entity_count, client_idx)

        # Bind click event
        if not hasattr(canvas, 'click_bound') or not canvas.click_bound:
            canvas.bind("<Button-1>", lambda event, c=canvas: self._handle_minimap_click(event, c))
            canvas.click_bound = True

########### START - STOP ################
    async def start(self):
        """Start the minimap update cycle"""
        if self.running or not self.clients:
            return
        
        self._create_windows()
        if not self.windows:
            return
        
        self.running = True
        self.update_thread = threading.Thread(target=self._update_loop, daemon=True)
        self.update_thread.start()
        
        if self.windows:
            self.windows[0].after(50, self.update)
        else:
            self.running = False
    
    async def stop(self):
        """Stop the minimap and clean up resources"""
        if not self.running:
            return
            
        self.running = False
        
        # Stop update thread
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
                tk_running = False
                try:
                    tk_running = tk._default_root and tk._default_root.winfo_exists()
                except:
                    pass
                
                if tk_running:
                    def destroy_safely():
                        for window in windows_to_destroy:
                            try:
                                if window.winfo_exists():
                                    window.destroy()
                            except:
                                pass
                    
                    if threading.current_thread() is threading.main_thread():
                        destroy_safely()
                    elif windows_to_destroy and hasattr(windows_to_destroy[0], 'after_idle'):
                        windows_to_destroy[0].after_idle(destroy_safely)
            except:
                pass
        
        # Clear queues
        for queue_attr in ['entity_queue', 'teleport_queue']:
            if hasattr(self, queue_attr):
                while not getattr(self, queue_attr).empty():
                    try:
                        getattr(self, queue_attr).get_nowait()
                    except:
                        pass