import customtkinter as ctk
from tkinter import messagebox, Canvas
import sys

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class SSHTunnelApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("SSH Tunnel Manager - MobaXterm Style")
        self.geometry("1100x750")
        self.minsize(900, 650)

        self.tunnels = []

        self._create_layout()
        self._add_demo_tunnels()
        self.protocol("WM_DELETE_WINDOW", self._on_exit)

    def _create_layout(self):
        self.grid_columnconfigure(0, weight=1, minsize=200)
        self.grid_columnconfigure(1, weight=4)
        self.grid_rowconfigure(0, weight=1)

        self.left_frame = ctk.CTkFrame(self, corner_radius=15)
        self.left_frame.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)
        self.left_frame.grid_rowconfigure(5, weight=1)

        btn_common = {
            "corner_radius": 8,
            "height": 45,
            "font": ctk.CTkFont(size=14, weight="bold")
        }

        self.btn_new = ctk.CTkButton(
            self.left_frame, text="New SSH tunnel", command=self._new_tunnel,
            fg_color="#2c3e66", hover_color="#3a5a8f", **btn_common
        )
        self.btn_new.pack(pady=(30, 15), padx=20, fill="x")

        self.btn_start_all = ctk.CTkButton(
            self.left_frame, text="Start all tunnels", command=self._start_all_tunnels,
            fg_color="#2c3e66", hover_color="#3a5a8f", **btn_common
        )
        self.btn_start_all.pack(pady=10, padx=20, fill="x")

        self.btn_stop_all = ctk.CTkButton(
            self.left_frame, text="Stop all tunnels", command=self._stop_all_tunnels,
            fg_color="#2c3e66", hover_color="#3a5a8f", **btn_common
        )
        self.btn_stop_all.pack(pady=10, padx=20, fill="x")

        self.btn_exit = ctk.CTkButton(
            self.left_frame, text="Exit", command=self._on_exit,
            fg_color="#8b3a3a", hover_color="#a04e4e", **btn_common
        )
        self.btn_exit.pack(pady=(10, 20), padx=20, fill="x")

        ctk.CTkLabel(self.left_frame, text="").pack(pady=10)

        self.right_frame = ctk.CTkFrame(self, corner_radius=15)
        self.right_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=10)
        self.right_frame.grid_columnconfigure(0, weight=1)
        self.right_frame.grid_rowconfigure(3, weight=1)

        self.forwarding_frame = ctk.CTkFrame(self.right_frame, corner_radius=10)
        self.forwarding_frame.grid(row=0, column=0, padx=15, pady=(15, 10), sticky="ew")

        self.forwarding_var = ctk.StringVar(value="local")
        radio_local = ctk.CTkRadioButton(
            self.forwarding_frame, text="Local port forwarding",
            variable=self.forwarding_var, value="local"
        )
        radio_local.grid(row=0, column=0, padx=20, pady=10, sticky="w")
        radio_remote = ctk.CTkRadioButton(
            self.forwarding_frame, text="Remote port forwarding",
            variable=self.forwarding_var, value="remote"
        )
        radio_remote.grid(row=0, column=1, padx=20, pady=10, sticky="w")
        radio_dynamic = ctk.CTkRadioButton(
            self.forwarding_frame, text="Dynamic port forwarding (SOCKS proxy)",
            variable=self.forwarding_var, value="dynamic"
        )
        radio_dynamic.grid(row=0, column=2, padx=20, pady=10, sticky="w")

        self.config_frame = ctk.CTkFrame(self.right_frame, corner_radius=10)
        self.config_frame.grid(row=1, column=0, padx=15, pady=10, sticky="ew")
        self.config_frame.grid_columnconfigure(0, weight=1)
        self.config_frame.grid_columnconfigure(1, weight=1)

        ssh_info_frame = ctk.CTkFrame(self.config_frame, fg_color="transparent")
        ssh_info_frame.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="nsew")
        ctk.CTkLabel(
            ssh_info_frame, text="SSH Server Configuration",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", pady=(0, 10))
        self.ssh_server_entry = ctk.CTkEntry(
            ssh_info_frame, placeholder_text="<SSH server>  e.g., 192.168.1.100"
        )
        self.ssh_server_entry.pack(fill="x", pady=5)
        self.ssh_user_entry = ctk.CTkEntry(
            ssh_info_frame, placeholder_text="<defaultuser>  e.g., root"
        )
        self.ssh_user_entry.pack(fill="x", pady=5)
        self.ssh_port_entry = ctk.CTkEntry(ssh_info_frame, placeholder_text="22", width=120)
        self.ssh_port_entry.pack(anchor="w", pady=5)
        self.ssh_port_entry.insert(0, "22")

        tunnel_params_frame = ctk.CTkFrame(self.config_frame, fg_color="transparent")
        tunnel_params_frame.grid(row=0, column=1, padx=(5, 10), pady=10, sticky="nsew")
        ctk.CTkLabel(
            tunnel_params_frame, text="Tunnel Parameters",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", pady=(0, 10))
        self.local_port_entry = ctk.CTkEntry(
            tunnel_params_frame, placeholder_text="Local port"
        )
        self.local_port_entry.pack(fill="x", pady=5)
        self.target_host_entry = ctk.CTkEntry(
            tunnel_params_frame, placeholder_text="Target host (for local/remote)"
        )
        self.target_host_entry.pack(fill="x", pady=5)
        self.target_port_entry = ctk.CTkEntry(
            tunnel_params_frame, placeholder_text="Target port"
        )
        self.target_port_entry.pack(fill="x", pady=5)

        self.btn_add_tunnel = ctk.CTkButton(
            self.config_frame, text="+ Create New Tunnel", command=self._add_tunnel_from_form,
            fg_color="#2c6e4f", hover_color="#3d8b63", corner_radius=8, height=40,
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.btn_add_tunnel.grid(row=1, column=0, columnspan=2, pady=(10, 5), padx=20, sticky="ew")

        tunnel_list_label = ctk.CTkLabel(
            self.right_frame, text="Tunnels List", font=ctk.CTkFont(size=15, weight="bold")
        )
        tunnel_list_label.grid(row=2, column=0, padx=15, pady=(10, 0), sticky="w")

        self.tunnel_list_frame = ctk.CTkScrollableFrame(self.right_frame, corner_radius=10, height=200)
        self.tunnel_list_frame.grid(row=3, column=0, padx=15, pady=(5, 10), sticky="nsew")
        self._refresh_tunnel_list()

        diagram_label = ctk.CTkLabel(
            self.right_frame, text="SSH Tunnel Diagram (MobaXterm Style)",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        diagram_label.grid(row=4, column=0, padx=15, pady=(5, 0), sticky="w")

        self.diagram_frame = ctk.CTkFrame(self.right_frame, corner_radius=10, height=220)
        self.diagram_frame.grid(row=5, column=0, padx=15, pady=(5, 15), sticky="ew")
        self.diagram_frame.grid_propagate(False)
        self.diagram_frame.bind("<Configure>", self._draw_diagram)

    def _draw_diagram(self, event=None):
        width = self.diagram_frame.winfo_width()
        height = self.diagram_frame.winfo_height()
        if width < 50 or height < 50:
            return

        if hasattr(self, '_diagram_canvas'):
            self._diagram_canvas.destroy()

        canvas = Canvas(self.diagram_frame, width=width, height=height, bg="#1e1e2e", highlightthickness=0)
        canvas.place(x=0, y=0, width=width, height=height)
        self._diagram_canvas = canvas

        box_color = "#3a4a6e"
        text_color = "#ffffff"
        line_color = "#6c8ebf"

        cw, ch = width, height
        box_w, box_h = 140, 50

        x_local, y_local = 30, ch // 2 - 30
        canvas.create_rectangle(x_local, y_local, x_local + box_w, y_local + box_h,
                                fill=box_color, outline="#8aa9d6", width=2)
        canvas.create_text(x_local + box_w//2, y_local + box_h//2 - 8,
                           text="My computer", fill=text_color, font=("Segoe UI", 10, "bold"))
        canvas.create_text(x_local + box_w//2, y_local + box_h//2 + 8,
                           text="with MobaXterm", fill="#bbbbdd", font=("Segoe UI", 9))
        canvas.create_text(x_local + box_w//2, y_local - 15,
                           text="Local clients", fill="#c0e0ff", font=("Segoe UI", 9, "italic"))

        # SSH Tunnel
        x_tunnel, y_tunnel = x_local + box_w + 50, ch // 2 - 30
        canvas.create_rectangle(x_tunnel, y_tunnel, x_tunnel + box_w, y_tunnel + box_h,
                                fill=box_color, outline="#8aa9d6", width=2)
        canvas.create_text(x_tunnel + box_w//2, y_tunnel + box_h//2,
                           text="SSH Tunnel", fill=text_color, font=("Segoe UI", 10, "bold"))

        # Firewall
        x_fw, y_fw = x_tunnel + box_w + 50, ch // 2 - 30
        canvas.create_rectangle(x_fw, y_fw, x_fw + box_w, y_fw + box_h,
                                fill="#5a3e4e", outline="#d68c9c", width=2)
        canvas.create_text(x_fw + box_w//2, y_fw + box_h//2,
                           text="Firewall", fill=text_color, font=("Segoe UI", 10, "bold"))

        # Remote Server
        x_remote, y_remote = x_fw + box_w + 50, ch // 2 - 30
        canvas.create_rectangle(x_remote, y_remote, x_remote + box_w, y_remote + box_h,
                                fill=box_color, outline="#8aa9d6", width=2)
        canvas.create_text(x_remote + box_w//2, y_remote + box_h//2 - 8,
                           text="Remote server", fill=text_color, font=("Segoe UI", 10, "bold"))
        canvas.create_text(x_remote + box_w//2, y_remote + box_h//2 + 8,
                           text="<Remote server>", fill="#bbbbdd", font=("Segoe UI", 9))
        canvas.create_text(x_remote + box_w//2, y_remote + box_h + 15,
                           text="<Remote port>   <Forwarded port>", fill="#aaccff", font=("Segoe UI", 9))

        canvas.create_line(x_local + box_w, y_local + box_h//2, x_tunnel, y_tunnel + box_h//2,
                           fill=line_color, width=2, arrow="last", arrowshape=(8,10,4))
        canvas.create_line(x_tunnel + box_w, y_tunnel + box_h//2, x_fw, y_fw + box_h//2,
                           fill=line_color, width=2, arrow="last", arrowshape=(8,10,4))
        canvas.create_line(x_fw + box_w, y_fw + box_h//2, x_remote, y_remote + box_h//2,
                           fill=line_color, width=2, arrow="last", arrowshape=(8,10,4))

        canvas.create_text((x_local + x_tunnel)//2, y_local - 25,
                           text="Connection from local", fill="#cceeff", font=("Segoe UI", 9))
        canvas.create_text((x_local + x_tunnel)//2, y_local - 12,
                           text="applications to remote server", fill="#cceeff", font=("Segoe UI", 9))

        canvas.create_text(40, ch - 25, text="SSH server:", anchor="w",
                           fill="#ffd966", font=("Segoe UI", 9, "bold"))
        canvas.create_text(120, ch - 25,
                           text=f"<{self.ssh_server_entry.get() or 'SSH Server'}>",
                           anchor="w", fill="#ffd966", font=("Segoe UI", 9))
        canvas.create_text(40, ch - 10,
                           text=f"User: {self.ssh_user_entry.get() or 'defaultuser'} / Port: {self.ssh_port_entry.get() or '22'}",
                           anchor="w", fill="#ffd966", font=("Segoe UI", 9))

        fwd_type = self.forwarding_var.get()
        type_str = "Local Forwarding" if fwd_type == "local" else ("Remote Forwarding" if fwd_type == "remote" else "Dynamic SOCKS")
        canvas.create_text(width - 20, 20, text=f"Active mode: {type_str}",
                           anchor="ne", fill="#8bc34a", font=("Segoe UI", 9, "italic"))

    def _add_demo_tunnels(self):
        demo1 = {
            "type": "local", "local_port": "8080", "target_host": "localhost", "target_port": "80",
            "ssh_server": "192.168.1.100", "ssh_user": "admin", "ssh_port": "22", "status": "Stopped"
        }
        demo2 = {
            "type": "dynamic", "local_port": "1080", "target_host": "", "target_port": "",
            "ssh_server": "vps.example.com", "ssh_user": "root", "ssh_port": "22", "status": "Stopped"
        }
        self.tunnels.extend([demo1, demo2])
        self._refresh_tunnel_list()

    def _refresh_tunnel_list(self):
        for widget in self.tunnel_list_frame.winfo_children():
            widget.destroy()

        if not self.tunnels:
            empty_label = ctk.CTkLabel(self.tunnel_list_frame, text="No tunnels created. Click 'Create New Tunnel' to add.")
            empty_label.pack(pady=20)
            return

        for idx, tunnel in enumerate(self.tunnels):
            card = ctk.CTkFrame(self.tunnel_list_frame, corner_radius=8, border_width=1, border_color="#3a5a7a")
            card.pack(pady=5, padx=5, fill="x")
            card.grid_columnconfigure(1, weight=1)

            type_display = {"local": "Local", "remote": "Remote", "dynamic": "Dynamic(SOCKS)"}.get(tunnel['type'], "Unknown")
            status_color = "#4caf50" if tunnel['status'] == "Running" else "#9e9e9e"
            info_text = f"[{type_display}]  Local Port: {tunnel['local_port']}"
            if tunnel['type'] in ('local', 'remote'):
                info_text += f"  →  Target: {tunnel['target_host']}:{tunnel['target_port']}"
            info_text += f"  |  SSH: {tunnel['ssh_user']}@{tunnel['ssh_server']}:{tunnel['ssh_port']}"

            lbl_info = ctk.CTkLabel(card, text=info_text, font=ctk.CTkFont(size=12), anchor="w")
            lbl_info.grid(row=0, column=0, padx=10, pady=10, sticky="w")

            status_lbl = ctk.CTkLabel(card, text=tunnel['status'], font=ctk.CTkFont(size=11, weight="bold"), text_color=status_color)
            status_lbl.grid(row=0, column=1, padx=10, pady=10, sticky="e")

            btn_frame = ctk.CTkFrame(card, fg_color="transparent")
            btn_frame.grid(row=0, column=2, padx=5, pady=5, sticky="e")

            start_btn = ctk.CTkButton(btn_frame, text="▶ Start", width=60, height=28, fg_color="#2c6e4f",
                                      command=lambda i=idx: self._start_tunnel(i))
            start_btn.pack(side="left", padx=2)
            stop_btn = ctk.CTkButton(btn_frame, text="■ Stop", width=60, height=28, fg_color="#8b5a2b",
                                     command=lambda i=idx: self._stop_tunnel(i))
            stop_btn.pack(side="left", padx=2)
            del_btn = ctk.CTkButton(btn_frame, text="✕", width=40, height=28, fg_color="#8b3a3a",
                                    command=lambda i=idx: self._delete_tunnel(i))
            del_btn.pack(side="left", padx=2)

    def _add_tunnel_from_form(self):
        fwd_type = self.forwarding_var.get()
        local_port = self.local_port_entry.get().strip()
        target_host = self.target_host_entry.get().strip()
        target_port = self.target_port_entry.get().strip()
        ssh_server = self.ssh_server_entry.get().strip()
        ssh_user = self.ssh_user_entry.get().strip() or "defaultuser"
        ssh_port = self.ssh_port_entry.get().strip() or "22"

        if not local_port.isdigit():
            messagebox.showerror("Error", "Local port must be a number.")
            return
        if not ssh_server:
            messagebox.showerror("Error", "SSH server address is required.")
            return
        if fwd_type in ('local', 'remote') and (not target_host or not target_port.isdigit()):
            messagebox.showerror("Error", "Target host and port are required for local/remote forwarding.")
            return

        new_tunnel = {
            "type": fwd_type,
            "local_port": local_port,
            "target_host": target_host if fwd_type != 'dynamic' else "",
            "target_port": target_port if fwd_type != 'dynamic' else "",
            "ssh_server": ssh_server,
            "ssh_user": ssh_user,
            "ssh_port": ssh_port,
            "status": "Stopped"
        }
        self.tunnels.append(new_tunnel)
        self._refresh_tunnel_list()
        messagebox.showinfo("Success", f"New {fwd_type} tunnel added.")
        self.local_port_entry.delete(0, 'end')
        self.target_host_entry.delete(0, 'end')
        self.target_port_entry.delete(0, 'end')

    def _start_tunnel(self, idx):
        self.tunnels[idx]['status'] = "Running"
        self._refresh_tunnel_list()

    def _stop_tunnel(self, idx):
        self.tunnels[idx]['status'] = "Stopped"
        self._refresh_tunnel_list()

    def _delete_tunnel(self, idx):
        del self.tunnels[idx]
        self._refresh_tunnel_list()

    def _start_all_tunnels(self):
        for t in self.tunnels:
            t['status'] = "Running"
        self._refresh_tunnel_list()
        messagebox.showinfo("Start All", "All tunnels started (simulation).")

    def _stop_all_tunnels(self):
        for t in self.tunnels:
            t['status'] = "Stopped"
        self._refresh_tunnel_list()
        messagebox.showinfo("Stop All", "All tunnels stopped (simulation).")

    def _new_tunnel(self):
        self.local_port_entry.focus()
        messagebox.showinfo("New Tunnel", "Please fill the tunnel parameters on the right side and click 'Create New Tunnel'.")

    def _on_exit(self):
        if messagebox.askyesno("Exit", "Are you sure you want to exit?"):
            self.quit()
            self.destroy()

if __name__ == "__main__":
    app = SSHTunnelApp()
    app.mainloop()