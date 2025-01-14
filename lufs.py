import sys
import subprocess
import json
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, 
    QTextEdit, QCheckBox, QSpinBox, QComboBox, QFileDialog
)
from PyQt5.QtCore import QThread, pyqtSignal, QRunnable, QThreadPool, QObject

# 自定义信号类
class LogSignal(QObject):
    log_message = pyqtSignal(str)  # 定义一个信号，用于传递日志信息

# 用于执行耗时任务的 Worker
class Worker(QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.log_signal = LogSignal()  # 创建信号对象

    def run(self):
        self.fn(*self.args, **self.kwargs, log_signal=self.log_signal)

# 主界面类
class LUFSNormalizer(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.thread_pool = QThreadPool()  # 线程池

    def initUI(self):
        self.setWindowTitle('MP4视频音频响度处理工具')
        self.setGeometry(100, 100, 800, 600)

        layout = QVBoxLayout()

        # 输入MP4路径
        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel('输入MP4路径:'))
        self.input_path = QLineEdit()
        input_layout.addWidget(self.input_path)
        self.input_browse_button = QPushButton('浏览')
        self.input_browse_button.clicked.connect(self.browse_input_file)
        input_layout.addWidget(self.input_browse_button)
        layout.addLayout(input_layout)

        # 输出MP4路径
        output_layout = QHBoxLayout()
        output_layout.addWidget(QLabel('输出MP4路径:'))
        self.output_path = QLineEdit()
        output_layout.addWidget(self.output_path)
        self.output_browse_button = QPushButton('浏览')
        self.output_browse_button.clicked.connect(self.browse_output_file)
        output_layout.addWidget(self.output_browse_button)
        layout.addLayout(output_layout)

        # 音频分析按钮
        self.analyze_button = QPushButton('音频分析')
        self.analyze_button.clicked.connect(self.analyze_audio)
        layout.addWidget(self.analyze_button)

        # 自定义分析参数
        self.loudnorm_params = {}
        params = ['I', 'TP', 'LRA', 'measured_I', 'measured_TP', 'measured_LRA', 'measured_thresh', 'offset']
        for param in params:
            param_layout = QHBoxLayout()
            param_layout.addWidget(QLabel(f'{param}:'))
            self.loudnorm_params[param] = QLineEdit()
            param_layout.addWidget(self.loudnorm_params[param])
            layout.addLayout(param_layout)

        # 设置默认值
        self.loudnorm_params['I'].setText('-14')
        self.loudnorm_params['TP'].setText('-1.5')
        self.loudnorm_params['LRA'].setText('11')

        # 音频分析时长
        duration_layout = QHBoxLayout()
        duration_layout.addWidget(QLabel('音频分析时长(秒):'))
        self.duration = QSpinBox()
        self.duration.setRange(0, 3600)
        duration_layout.addWidget(self.duration)
        layout.addLayout(duration_layout)

        # 自定义音频比特率、编码格式和采样频率
        audio_layout = QHBoxLayout()
        audio_layout.addWidget(QLabel('音频比特率:'))
        self.bitrate = QLineEdit('192K')
        audio_layout.addWidget(self.bitrate)
        audio_layout.addWidget(QLabel('编码格式:'))
        self.codec = QComboBox()
        self.codec.addItems(['aac', 'mp3', 'flac'])
        audio_layout.addWidget(self.codec)
        audio_layout.addWidget(QLabel('采样频率:'))
        self.sample_rate = QLineEdit('44100')
        audio_layout.addWidget(self.sample_rate)
        layout.addLayout(audio_layout)

        # 启用Intel QSV硬件加速
        self.hw_accel = QCheckBox('启用 Intel QSV 硬件加速')
        layout.addWidget(self.hw_accel)

        # 处理音频（视频无损）按钮
        self.process_button = QPushButton('处理音频（视频无损）')
        self.process_button.clicked.connect(self.process_audio)
        layout.addWidget(self.process_button)

        # 日志输出
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        layout.addWidget(self.log_output)

        self.setLayout(layout)

    def browse_input_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, '选择输入MP4文件', '', 'MP4文件 (*.mp4)')
        if file_path:
            self.input_path.setText(file_path)

    def browse_output_file(self):
        file_path, _ = QFileDialog.getSaveFileName(self, '选择输出MP4文件', '', 'MP4文件 (*.mp4)')
        if file_path:
            self.output_path.setText(file_path)

    def analyze_audio(self):
        input_file = self.input_path.text()
        if not input_file:
            self.log_output.append('请输入输入MP4路径')
            return

        # 将耗时任务放入线程池
        worker = Worker(self.run_analyze_audio, input_file)
        worker.log_signal.log_message.connect(self.update_log)  # 连接信号槽
        self.thread_pool.start(worker)

    def run_analyze_audio(self, input_file, log_signal):
        duration = self.duration.value()
        ffmpeg_cmd = ['ffmpeg', '-i', input_file]
        if duration > 0:
            ffmpeg_cmd.extend(['-t', str(duration)])
        ffmpeg_cmd.extend(['-af', 'loudnorm=print_format=json', '-f', 'null', '-'])

        log_signal.log_message.emit('开始音频分析...')
        try:
            # 实时读取 FFmpeg 输出
            process = subprocess.Popen(ffmpeg_cmd, stderr=subprocess.PIPE, encoding='utf-8', text=True)
            output = ""
            for line in process.stderr:
                output += line
                log_signal.log_message.emit(line.strip())
            process.wait()

            # 解析 FFmpeg 输出
            self.parse_loudnorm_output(output)
        except subprocess.CalledProcessError as e:
            log_signal.log_message.emit(f'FFmpeg 执行失败: {e.stderr}')
        except UnicodeDecodeError as e:
            log_signal.log_message.emit(f'编码错误: {str(e)}')
        except Exception as e:
            log_signal.log_message.emit(f'音频分析失败: {str(e)}')

    def parse_loudnorm_output(self, output):
        try:
            # 从输出中提取 JSON 数据
            json_start = output.find('{')
            json_end = output.rfind('}') + 1
            if json_start == -1 or json_end == -1:
                raise ValueError("未找到有效的 JSON 数据")

            json_data = output[json_start:json_end]
            data = json.loads(json_data)

            # 将解析的数据填充到对应的输入框中
            self.loudnorm_params['measured_I'].setText(str(data['input_i']))
            self.loudnorm_params['measured_TP'].setText(str(data['input_tp']))
            self.loudnorm_params['measured_LRA'].setText(str(data['input_lra']))
            self.loudnorm_params['measured_thresh'].setText(str(data['input_thresh']))
            self.loudnorm_params['offset'].setText(str(data['target_offset']))
        except Exception as e:
            self.log_output.append(f'解析音频分析结果失败: {str(e)}')

    def process_audio(self):
        input_file = self.input_path.text()
        output_file = self.output_path.text()
        if not input_file or not output_file:
            self.log_output.append('请输入输入和输出MP4路径')
            return

        # 将耗时任务放入线程池
        worker = Worker(self.run_process_audio, input_file, output_file)
        worker.log_signal.log_message.connect(self.update_log)  # 连接信号槽
        self.thread_pool.start(worker)

    def run_process_audio(self, input_file, output_file, log_signal):
        # 获取用户自定义参数
        I = self.loudnorm_params['I'].text()
        TP = self.loudnorm_params['TP'].text()
        LRA = self.loudnorm_params['LRA'].text()
        measured_I = self.loudnorm_params['measured_I'].text()
        measured_TP = self.loudnorm_params['measured_TP'].text()
        measured_LRA = self.loudnorm_params['measured_LRA'].text()
        measured_thresh = self.loudnorm_params['measured_thresh'].text()
        offset = self.loudnorm_params['offset'].text()

        # 获取音频参数
        bitrate = self.bitrate.text()
        codec = self.codec.currentText()
        sample_rate = self.sample_rate.text()

        # 构建 FFmpeg 命令
        ffmpeg_cmd = ['ffmpeg']

        # 如果启用硬件加速
        if self.hw_accel.isChecked():
            ffmpeg_cmd.extend([
                '-hwaccel', 'qsv',  # 硬件加速解码
                '-hwaccel_output_format', 'qsv',  # 硬件加速输出格式
                '-extra_hw_frames', '16'  # 增加硬件帧缓冲区
            ])

        # 输入文件
        ffmpeg_cmd.extend(['-i', input_file])

        # 音频处理参数
        ffmpeg_cmd.extend([
            '-af', f'loudnorm=I={I}:TP={TP}:LRA={LRA}:measured_I={measured_I}:measured_TP={measured_TP}:measured_LRA={measured_LRA}:measured_thresh={measured_thresh}:offset={offset}',
            '-b:a', bitrate,
            '-ar', sample_rate,
            '-ac', '2',  # 立体声
            '-c:v', 'copy',  # 直接复制视频流，保持无损
            '-c:a', codec,  # 处理音频流
            output_file
        ])

        log_signal.log_message.emit('开始处理音频（视频无损）...')
        try:
            # 实时读取 FFmpeg 输出
            process = subprocess.Popen(ffmpeg_cmd, stderr=subprocess.PIPE, encoding='utf-8', text=True)
            for line in process.stderr:
                log_signal.log_message.emit(line.strip())
            process.wait()
            log_signal.log_message.emit('音频处理完成！')
        except subprocess.CalledProcessError as e:
            log_signal.log_message.emit(f'FFmpeg 执行失败: {e.stderr}')
        except UnicodeDecodeError as e:
            log_signal.log_message.emit(f'编码错误: {str(e)}')
        except Exception as e:
            log_signal.log_message.emit(f'音频处理失败: {str(e)}')

    def update_log(self, message):
        """更新日志输出"""
        self.log_output.append(message)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = LUFSNormalizer()
    ex.show()
    sys.exit(app.exec_())
