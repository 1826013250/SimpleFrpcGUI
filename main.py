import os
import sys
import re
import subprocess
import tkinter as tk
from tkinter.messagebox import showerror, showwarning
from multiprocessing import Process, Queue
from threading import Thread
from time import sleep

from configparser import ConfigParser


def process_work(queue, signal):
    if os.name == "nt":
        process = subprocess.Popen(["./frpc.exe"],
                                   stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE,
                                   text=True,
                                   bufsize=1,
                                   creationflags=0x08000000)
    else:
        process = subprocess.Popen(["./frpc"],
                                   stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE,
                                   text=True,
                                   bufsize=1)

    def get_message(process, queue):
        for i in iter(process.stdout.readline, ''):
            queue.put(i)

    thr = Thread(target=get_message, args=(process, queue))
    thr.start()
    while True:
        sleep(0.5)
        if not thr.is_alive():
            queue.put("process_shutdown")
            break
        if not signal.empty():
            sig = signal.get()
            if sig == "stop":
                process.terminate()
                if thr.is_alive():
                    thr.join()
                queue.put("process_shutdown")
                break
            if sig == "restart":
                process.terminate()
                if thr.is_alive():
                    thr.join()
                queue.put("process_restart")
                break


class Settings:
    def __init__(self,
                 server_ip="example.com",
                 server_port=7000,
                 token="password",
                 service_name="test service name here",
                 service_type="tcp",
                 local_ip="127.0.0.1",
                 local_port=11451,
                 remote_port=25565):
        self.server_ip = tk.StringVar(value=server_ip)
        self.server_port = tk.IntVar(value=server_port)
        self.token = tk.StringVar(value=token)
        self.service_name = tk.StringVar(value=service_name)
        self.service_type = tk.StringVar(value=service_type)
        self.local_ip = tk.StringVar(value=local_ip)
        self.local_port = tk.IntVar(value=local_port)
        self.remote_port = tk.IntVar(value=remote_port)


newObject = object()


def load_settings():
    if os.path.exists("./frpc.ini"):
        try:
            cnf = ConfigParser()
            cnf.read("./frpc.ini")
            service_name = cnf.sections()[-1]
            settings = Settings(
                server_ip=cnf["common"]["server_addr"],
                server_port=int(cnf["common"]["server_port"]),
                token=cnf["common"]["token"],
                service_name=cnf.sections()[-1],
                service_type=cnf[service_name]["type"],
                local_ip=cnf[service_name]["local_ip"],
                local_port=int(cnf[service_name]["local_port"]),
                remote_port=int(cnf[service_name]["remote_port"])
            )
            return settings
        except (KeyError, ValueError):
            settings = Settings()
            save_settings(settings)
            return settings
    else:
        settings = Settings()
        save_settings(settings)
        return settings


def save_settings(settings):
    cnf = ConfigParser()
    cnf.add_section("common")
    cnf.add_section(settings.service_name.get())
    cnf.set("common", "server_addr", settings.server_ip.get())
    cnf.set("common", "server_port", str(settings.server_port.get()))
    cnf.set("common", "token", settings.token.get())
    cnf.set(settings.service_name.get(), "type", settings.service_type.get())
    cnf.set(settings.service_name.get(), "local_ip", settings.local_ip.get())
    cnf.set(settings.service_name.get(), "local_port", str(settings.local_port.get()))
    cnf.set(settings.service_name.get(), "remote_port", str(settings.remote_port.get()))
    with open("./frpc.ini", 'w') as f:
        cnf.write(f)


class Gui(tk.Tk):
    def __init__(self):
        super().__init__()
        self.status = tk.StringVar(value="未知")
        self.queue = Queue()
        self.kill_signal = Queue()
        self.settings = load_settings()
        self.process = Process()
        self.init_widgets()
        self.wm_geometry("+%d+%d" % (self.winfo_screenheight() // 4, self.winfo_screenwidth() // 4))
        self.wm_title("Frpc 启动器")
        self.after(1, self.update_status)
        self.protocol("WM_DELETE_WINDOW", self.close_window)

    def close_window(self):
        self.kill_signal.put("stop")
        if self.process.is_alive():
            self.queue.get()
        self.destroy()

    def init_widgets(self):
        text_frame = tk.LabelFrame(self, text="当前状态:")
        text_frame.pack()
        self.status_label = tk.Label(text_frame, textvariable=self.status)
        self.status_label.pack(side=tk.RIGHT)

        button_frame = tk.Frame(self)
        button_frame.pack()
        button_start = tk.Button(button_frame, text="启动", command=self.start)
        button_start.pack(side=tk.LEFT)
        button_term = tk.Button(button_frame, text="关闭", command=lambda: self.kill_signal.put("stop")
                                if self.status.get() in ["启动中", "运行中"] else ...)
        button_term.pack(side=tk.LEFT)
        button_settings = tk.Button(button_frame, text="设置", command=lambda: SettingMenu(self))
        button_settings.pack(side=tk.LEFT)

        info_label = tk.LabelFrame(self, text="Frpc 日志")
        info_label.pack(fill=tk.BOTH, expand=tk.YES)
        self.info = tk.Text(info_label)
        self.info.pack(fill=tk.BOTH, expand=tk.YES)

    def start(self):
        if self.status.get() in ["未知", "关闭"]:
            self.info.delete(1.0, 'end')
            self.status.set("启动中")
            self.process = Process(target=process_work, args=(self.queue, self.kill_signal))
            self.process.start()

    def update_status(self):
        if not self.queue.empty():
            current_text = self.queue.get()
            print(current_text, end="")
            if "start proxy success" in current_text:
                self.status.set("运行中")
                self.insert_text("\x1b[1;33m#####提示#####\n")
                self.insert_text("\x1b[1;34mFrpc启动成功!\n")
                self.insert_text("\x1b[1;34m请使用外部IP: [%s:%s] 来连接!\n" % (self.settings.server_ip.get(),
                                 self.settings.remote_port.get()))
                self.insert_text("\x1b[1;33m#####提示#####\n")
            if "port already used" in current_text:
                self.insert_text("\x1b[1;33m#####警告#####\n")
                self.insert_text("\x1b[1;31m远程端口被占用,请更换端口(推荐)或等待其解除占用\n")
                self.insert_text("\x1b[1;33m#####警告#####\n")
            if "port not allowed" in current_text:
                self.insert_text("\x1b[1;33m#####警告#####\n")
                self.insert_text("\x1b[1;31m端口不允许,请使用0-65535之间任意一个数值\n")
                self.insert_text("\x1b[1;33m#####警告#####\n")
            if "0..65535" in current_text:
                self.insert_text("\x1b[1;33m#####警告#####\n")
                self.insert_text("\x1b[1;31m端口不允许,请使用0-65535之间任意一个数值\n")
                self.insert_text("\x1b[1;33m#####警告#####\n")
            if "error: dial" in current_text:
                self.insert_text("\x1b[1;33m#####错误#####\n")
                if "connection refused" in current_text:
                    self.insert_text("\x1b[1;31m本地服务拒绝连接\n")
                    self.insert_text("\x1b[1;31m请检查本地服务是否开启\n")
                elif "i/o time out" in current_text:
                    self.insert_text("\x1b[1;31m连接本地指定ip失败\n")
                    self.insert_text("\x1b[1;31m请检查本地服务是否开启以及ip是否正确\n")
                elif "invalid port" in current_text:
                    self.insert_text("\x1b[1;31m本地端口\"%s\"无效\n"
                                     % re.search(r": address (.*): invalid port", current_text).groups()[0])
                    self.insert_text("\x1b[1;31m请重新修改配置\n")
                self.insert_text("\x1b[1;33m#####错误#####\n")
            if "invalid type" in current_text:
                self.insert_text("\x1b[1;31m#####错误#####\n")
                self.insert_text("\x1b[1;33m穿透类型\"%s\"无效,请使用tcp, udp, http, https, stcp, sudp任意一种\n"
                                 % re.search(r"\[(.*)]", current_text).groups()[0])
                self.insert_text("\x1b[1;31m#####错误#####\n")
            if "login to server failed" in current_text:
                self.insert_text("\x1b[1;33m#####警告#####\n")
                if "no such host" in current_text:
                    self.insert_text("\x1b[1;31m未找到域名: %s\n"
                                     % re.search(r"lookup (.*):", current_text).groups())
                if "token in login doesn't match token from configuration" in current_text:
                    self.insert_text("\x1b[1;31mtoken令牌不正确, 请前往设置更改\n")
                if "network is unreachable" in current_text:
                    self.insert_text("\x1b[1;31m网络不可达, 请检查你的网络设置\n")
                self.insert_text("\x1b[1;33m#####警告#####\n")
            if current_text == "process_shutdown":
                self.status.set("关闭")
                self.insert_text("\x1b[1;31mFrpc已关闭\n")
                return self.after(20, self.update_status)
            elif current_text == "process_restart":
                self.status.set("关闭")
                self.insert_text("\x1b[1;31mFrpc正重启...\n")
                self.start()
                return self.after(20, self.update_status)
            self.insert_text(current_text)
        return self.after(20, self.update_status)

    def insert_text(self, text):
        self.info.tag_config("normal", foreground=None)
        self.info.tag_config("blue", foreground='blue')
        self.info.tag_config("yellow", foreground='orange')
        self.info.tag_config("red", foreground='red')
        texts = text.split("\x1b[") if "\x1b[" in text else text.split("\033")
        for i in texts:
            temp = self.info.index("end-1c")
            if i[:2] == "0m":
                self.info.insert(tk.END, i[2:])
                self.info.tag_add("normal", temp, self.info.index("end-1c"))
            elif i[:5] == "1;34m":
                self.info.insert(tk.END, i[5:])
                self.info.tag_add("blue", temp, self.info.index("end-1c"))
            elif i[:5] == "1;31m":
                self.info.insert(tk.END, i[5:])
                self.info.tag_add("red", temp, self.info.index("end-1c"))
            elif i[:5] == "1;33m":
                self.info.insert(tk.END, i[5:])
                self.info.tag_add("yellow", temp, self.info.index("end-1c"))
            else:
                self.info.insert(tk.END, i)


class SettingMenu(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master=master)
        self.init_widgets()
        self.wm_geometry("+%d+%d" % (master.winfo_x() + 20, master.winfo_y() + 20))
        self.focus_set()
        self.protocol("WM_DELETE_WINDOW", self.cancel)

    def init_widgets(self):
        serverip_frame = tk.Frame(self)
        serverip_frame.pack(fill=tk.X, expand=tk.YES)
        serverip_label = tk.Label(serverip_frame, text="服务器IP")
        serverip_label.pack(side=tk.LEFT)
        serverip_entry = tk.Entry(serverip_frame, textvariable=self.master.settings.server_ip,
                                  justify=tk.RIGHT, width=15)
        serverip_entry.pack(side=tk.RIGHT)

        server_port_frame = tk.Frame(self)
        server_port_frame.pack(fill=tk.X, expand=tk.YES)
        server_port_label = tk.Label(server_port_frame, text="服务器Frps服务端口")
        server_port_label.pack(side=tk.LEFT)
        server_port_entry = tk.Entry(server_port_frame, textvariable=self.master.settings.server_port,
                                     justify=tk.RIGHT, width=5)
        server_port_entry.pack(side=tk.RIGHT)

        token_frame = tk.Frame(self)
        token_frame.pack(fill=tk.X, expand=tk.YES)
        token_label = tk.Label(token_frame, text="服务器登陆令牌")
        token_label.pack(side=tk.LEFT)
        token_entry = tk.Entry(token_frame, textvariable=self.master.settings.token,
                               justify=tk.RIGHT, width=15)
        token_entry.pack(side=tk.RIGHT)

        service_name_frame = tk.Frame(self)
        service_name_frame.pack(fill=tk.X, expand=tk.YES)
        service_name_label = tk.Label(service_name_frame, text="Frp服务名")
        service_name_label.pack(side=tk.LEFT)
        service_name_entry = tk.Entry(service_name_frame, textvariable=self.master.settings.service_name,
                                      justify=tk.RIGHT, width=15)
        service_name_entry.pack(side=tk.RIGHT)

        frp_type_frame = tk.Frame(self)
        frp_type_frame.pack(fill=tk.X, expand=tk.YES)
        frp_type_label = tk.Label(frp_type_frame, text="穿透类型")
        frp_type_label.pack(side=tk.LEFT)
        frp_type_entry = tk.Entry(frp_type_frame, textvariable=self.master.settings.service_type,
                                  justify=tk.RIGHT, width=5)
        frp_type_entry.pack(side=tk.RIGHT)

        local_ip_frame = tk.Frame(self)
        local_ip_frame.pack(fill=tk.X, expand=tk.YES)
        local_ip_label = tk.Label(local_ip_frame, text="本地IP")
        local_ip_label.pack(side=tk.LEFT)
        local_ip_entry = tk.Entry(local_ip_frame, textvariable=self.master.settings.local_ip,
                                  justify=tk.RIGHT, width=15)
        local_ip_entry.pack(side=tk.RIGHT)

        local_port_frame = tk.Frame(self)
        local_port_frame.pack(fill=tk.X, expand=tk.YES)
        local_port_label = tk.Label(local_port_frame, text="本地端口")
        local_port_label.pack(side=tk.LEFT)
        local_port_entry = tk.Entry(local_port_frame, textvariable=self.master.settings.local_port,
                                    justify=tk.RIGHT, width=5)
        local_port_entry.pack(side=tk.RIGHT)

        remote_port_frame = tk.Frame(self)
        remote_port_frame.pack(fill=tk.X, expand=tk.YES)
        remote_port_label = tk.Label(remote_port_frame, text="远程端口")
        remote_port_label.pack(side=tk.LEFT)
        remote_port_entry = tk.Entry(remote_port_frame, textvariable=self.master.settings.remote_port,
                                     justify=tk.RIGHT, width=5)
        remote_port_entry.pack(side=tk.RIGHT)

        button_frame = tk.Frame(self)
        button_frame.pack()
        button_cancel = tk.Button(button_frame, text="取消", command=self.cancel)
        button_cancel.pack(side=tk.LEFT)
        button_confirm = tk.Button(button_frame, text="确定", command=self.confirm)
        button_confirm.pack(side=tk.RIGHT)

    def confirm(self):
        save_settings(self.master.settings)
        if self.master.status.get() in ["启动中", "运行中"]:
            self.master.kill_signal.put("restart")
            self.master.start()
        self.destroy()

    def cancel(self):
        self.master.settings = load_settings()
        self.destroy()


if __name__ == "__main__":
    if not os.path.exists("./frpc" + (".exe" if os.name == "nt" else "")):
        showerror("错误!", "未检测到Frpc！\n请尝试自行下载Frpc或者重新下载本程序！")
        showwarning("注意!",
                    "请检查目录下文件,Frpc客户端的文件名必须为\"%s\"\n若客户端是自己下载的请重新命名"
                    % ("frpc" + (".exe" if os.name == "nt" else "")))
    else:
        app = Gui()
        app.mainloop()
