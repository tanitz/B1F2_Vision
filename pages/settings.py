"""
Settings Page - ตั้งค่ากล้องและ Threshold
"""
import flet as ft
from config import theme

def create_settings_page():
    """สร้างหน้า Settings"""
    
    # Camera Settings
    camera_index = ft.TextField(
        value="0",
        width=120,
        text_style=ft.TextStyle(color=theme.TEXT_PRIMARY),
        bgcolor=ft.Colors.GREY_100,
        border_color=theme.ACCENT_BLUE,
    )
    
    resolution_dropdown = ft.Dropdown(
        value="1920x1080",
        options=[
            ft.dropdown.Option("640x480"),
            ft.dropdown.Option("1280x720"),
            ft.dropdown.Option("1920x1080"),
            ft.dropdown.Option("2560x1440"),
        ],
        width=200,
        text_style=ft.TextStyle(color=theme.TEXT_PRIMARY),
        bgcolor=ft.Colors.GREY_100,
        border_color=theme.ACCENT_BLUE,
    )
    
    # Threshold Slider
    confidence_slider = ft.Slider(
        min=0,
        max=100,
        value=70,
        divisions=100,
        label="{value}%",
        width=400,
        active_color=theme.ACCENT_BLUE,
    )
    
    confidence_value = ft.Text("70%", size=20, weight=ft.FontWeight.BOLD, color=theme.ACCENT_BLUE)
    
    def slider_changed(e):
        confidence_value.value = f"{int(e.control.value)}%"
        e.page.update()
    
    confidence_slider.on_change = slider_changed
    
    return ft.Container(
        content=ft.Column(
            [
                # Header
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(
                                "SETTINGS",
                                size=28,
                                weight=ft.FontWeight.BOLD,
                                color=theme.TEXT_PRIMARY,
                            ),
                            ft.Divider(color=ft.Colors.GREY_300, height=20),
                        ],
                    ),
                    padding=20,
                ),
                
                # Content
                ft.Container(
                    content=ft.Column(
                        [
                            # Camera Section
                            ft.Text(
                                "📷 Camera Settings",
                                size=20,
                                weight=ft.FontWeight.BOLD,
                                color=theme.TEXT_PRIMARY,
                            ),
                            ft.Divider(color=ft.Colors.GREY_300, height=20),
                            
                            ft.Row(
                                [
                                    ft.Text("Camera Index:", color=theme.TEXT_SECONDARY, width=150, size=16),
                                    camera_index,
                                ],
                                spacing=20,
                            ),
                            
                            ft.Row(
                                [
                                    ft.Text("Resolution:", color=theme.TEXT_SECONDARY, width=150, size=16),
                                    resolution_dropdown,
                                ],
                                spacing=20,
                            ),
                            
                            ft.Container(height=20),
                            
                            # Threshold Section
                            ft.Text(
                                "🎯 Detection Threshold",
                                size=20,
                                weight=ft.FontWeight.BOLD,
                                color=theme.TEXT_PRIMARY,
                            ),
                            ft.Divider(color=ft.Colors.GREY_300, height=20),
                            
                            ft.Row(
                                [
                                    ft.Text("Confidence:", color=theme.TEXT_SECONDARY, width=150, size=16),
                                    confidence_slider,
                                    confidence_value,
                                ],
                                spacing=20,
                                alignment=ft.MainAxisAlignment.START,
                            ),
                            
                            ft.Container(height=30),
                            
                            # Save Button
                            ft.ElevatedButton(
                                "💾 Save Settings",
                                bgcolor=theme.ACCENT_BLUE,
                                color=theme.TEXT_ON_ACTIVE,
                                width=200,
                                height=45,
                                style=ft.ButtonStyle(
                                    shape=ft.RoundedRectangleBorder(radius=8),
                                ),
                            ),
                        ],
                        spacing=12,
                        scroll=ft.ScrollMode.AUTO,
                    ),
                    padding=20,
                    expand=True,
                ),
            ],
            spacing=0,
        ),
        bgcolor=theme.BG_COLOR,
        expand=True,
    )
