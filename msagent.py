import sys
import os
import re
import argparse
import signal

from PySide6.QtCore import *
from PySide6.QtGui import *
from PySide6.QtWidgets import *
from PySide6.QtMultimedia import QSoundEffect, QAudioOutput


def _parseVal(value: str) -> object:
    value = value.strip().strip('"')
    if value.isdigit():
        return int(value)
    return value


def _addChild(parent: dict, key: str, child: dict) -> None:
    if key not in parent:
        parent[key] = child
    else:
        if isinstance(parent[key], list):
            parent[key].append(child)
        else:
            parent[key] = [parent[key], child]


def parseAcd(text: str) -> dict:
    data = {}
    stack = [("root", data)]

    startBlockPattern = re.compile(r"^\s*(Define\w+)(?:\s+(.*))?$")
    endBlockPattern = re.compile(r"^\s*(End\w+)\s*$")
    propertyPattern = re.compile(r"^\s*(\w+)\s*=\s*(.*)$")

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue

        startMatch = startBlockPattern.match(line)
        if startMatch:
            blockType = startMatch.group(1).replace("Define", "")
            arg = startMatch.group(2)
            newBlock = {}
            if arg:
                newBlock["id"] = _parseVal(arg)

            parentName, parentObj = stack[-1]
            _addChild(parentObj, blockType, newBlock)
            stack.append((blockType, newBlock))
            continue

        endMatch = endBlockPattern.match(line)
        if endMatch:
            if len(stack) > 1:
                stack.pop()
            continue

        propertyMatch = propertyPattern.match(line)
        if propertyMatch:
            key = propertyMatch.group(1)
            val = _parseVal(propertyMatch.group(2))
            _, currentObj = stack[-1]
            currentObj[key] = val
            continue

    return data


def loadAcd(acdPath: str) -> dict:
    if not os.path.isfile(acdPath):
        raise FileNotFoundError(f"ACD file not found: {acdPath}")
    with open(acdPath, "r", encoding="ISO-8859-1", errors="replace") as f:
        data = parseAcd(f.read())
    return data


def _asList(data: dict, key: str) -> list:
    val = data.get(key)
    if val is None:
        return []
    if isinstance(val, list):
        return val
    return [val]


def listAnimations(acdData: dict) -> list[str]:
    animations = []
    for animation in _asList(acdData, "Animation"):
        name = animation.get("id")
        if name and isinstance(name, str):
            animations.append(name)
    return sorted(animations)


def getAnimationData(acdData: dict, animationName: str) -> dict:
    for animation in _asList(acdData, "Animation"):
        if animation.get("id") == animationName:
            return animation
    return {}


class AnimationWorker(QObject):
    imageReady = Signal(QImage)
    playSoundSignal = Signal(str)
    animationFinished = Signal()

    def __init__(self, acdPath: str, data: dict, animations: list[str], 
                 speed: float, cycles: int):
        super().__init__()
        self.acdPath = acdPath
        self.data = data
        self.animations = animations
        self.speed = speed
        self.cycles = cycles
        self.defaultDuration = 10
        self._running = True
        self._imageCache = {}

    def stop(self):
        self._running = False

    def _preloadImages(self):
        baseDir = os.path.dirname(self.acdPath)
        
        def recurse_find_images(obj):
            if isinstance(obj, dict):
                if "Filename" in obj:
                    fname = obj["Filename"]
                    if fname not in self._imageCache:
                        path = os.path.join(baseDir, fname)
                        if os.path.isfile(path):
                            self._imageCache[fname] = QImage(path)
                for v in obj.values():
                    recurse_find_images(v)
            elif isinstance(obj, list):
                for item in obj:
                    recurse_find_images(item)

        recurse_find_images(self.data)

    def _applyTransparency(self, image: QImage) -> QImage:
        image = image.convertToFormat(QImage.Format_ARGB32)
        magenta = QColor(255, 0, 255).rgb()
        mask = image.createMaskFromColor(magenta, Qt.MaskOutColor)
        image.setAlphaChannel(mask)
        return image

    def run(self):
        self._preloadImages()
        
        charData = self.data.get("Character", {})
        if isinstance(charData, list): 
            charData = charData[0]
        self.defaultDuration = charData.get("DefaultFrameDuration", 10)

        loopCount = 0
        while self._running:
            if self.cycles != -1 and loopCount >= self.cycles:
                break
            
            for animationName in self.animations:
                if not self._running: break
                self._playAnimation(animationName)
            
            loopCount += 1

        self.animationFinished.emit()

    def _playAnimation(self, animationName):
        animationData = getAnimationData(self.data, animationName)
        if not animationData:
            return

        frames = _asList(animationData, "Frame")
        
        for frame in frames:
            if not self._running: return

            img = self._composeFrame(frame)
            if not img.isNull():
                self.imageReady.emit(img)

            soundEffect = frame.get("SoundEffect", None)
            if soundEffect:
                self.playSoundSignal.emit(soundEffect)

            rawDuration = frame.get("Duration", self.defaultDuration)
            msDuration = int((rawDuration * 10) / self.speed)
            QThread.msleep(max(10, msDuration))

    def _composeFrame(self, frame: dict) -> QImage:
        baseImage = QImage()
        images = _asList(frame, "Image")
        images.reverse()

        painter = QPainter()

        for imageEntry in images:
            imageName = imageEntry.get("Filename", "")
            if imageName not in self._imageCache:
                continue
            
            layerImg = self._imageCache[imageName]
            layerImg = self._applyTransparency(layerImg)
            
            if baseImage.isNull():
                baseImage = QImage(layerImg.size(), QImage.Format_ARGB32)
                baseImage.fill(Qt.transparent)
                painter.begin(baseImage)
            
            painter.drawImage(0, 0, layerImg)

        if painter.isActive():
            painter.end()
        elif not baseImage.isNull() and images:
             pass

        return baseImage


class MSAgentWidget(QLabel):
    animationFinished = Signal()

    def __init__(self, parent=None, acdPath="", animations=None, 
                 scale=1.0, volume=1.0, cycles=1, speed=1.0):
        super().__init__(parent)
        
        try:
            self.data = loadAcd(acdPath)
        except Exception as e:
            print(f"Error loading ACD: {e}")
            self.data = {}

        self.scale = scale
        self.volume = volume
        self.acdPath = acdPath
        
        # Cache for QSoundEffect objects
        self._soundEffects = {} 

        self._animationWorker = AnimationWorker(
            acdPath, self.data, animations or [], speed, cycles
        )

        self._animationWorker.imageReady.connect(self.updateFrame)
        self._animationWorker.playSoundSignal.connect(self.playSound)
        self._animationWorker.animationFinished.connect(self._onAnimationFinished)

        self._animationThread = QThread(self)
        self._animationWorker.moveToThread(self._animationThread)
        self._animationThread.started.connect(self._animationWorker.run)

    def start(self):
        self._animationThread.start()

    def closeEvent(self, event):
        self._animationWorker.stop()
        self._animationThread.quit()
        self._animationThread.wait()
        super().closeEvent(event)

    @Slot(QImage)
    def updateFrame(self, img: QImage):
        pixmap = QPixmap.fromImage(img)
        
        if self.scale != 1.0:
            pixmap = pixmap.scaled(
                int(pixmap.width() * self.scale), 
                int(pixmap.height() * self.scale), 
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )

        self.setPixmap(pixmap)

    @Slot(str)
    def playSound(self, filename: str):
        if filename in self._soundEffects:
            effect = self._soundEffects[filename]
            if effect.status() == QSoundEffect.Ready:
                effect.play()
            return

        soundPath = os.path.join(os.path.dirname(self.acdPath), filename)
        if not os.path.isfile(soundPath):
            return

        effect = QSoundEffect(self)
        effect.setSource(QUrl.fromLocalFile(soundPath))
        effect.setVolume(self.volume)
        
        # Keep reference so it doesn't get garbage collected
        self._soundEffects[filename] = effect
        
        effect.play()

    @Slot()
    def _onAnimationFinished(self):
        self._animationThread.quit()
        self.animationFinished.emit()


def main():
    parser = argparse.ArgumentParser(description="MS Agent Animation Player")
    parser.add_argument("acd_path", help="Path to the extracted .acd file")
    parser.add_argument("animations", nargs="?", default=None, help="Animation names, comma separated")
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--volume", type=float, default=1.0)
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--speed", type=float, default=1.0)

    args = parser.parse_args()

    if not os.path.isfile(args.acd_path):
        print(f"Error: ACD file not found at '{args.acd_path}'")
        sys.exit(1)

    if not args.animations:
        data = loadAcd(args.acd_path)
        print("Available animations:")
        for anim in listAnimations(data):
            print(f" - {anim}")
        sys.exit(0)

    os.environ["QT_LOGGING_RULES"] = "qt.multimedia.ffmpeg*=false"
    qapp = QApplication(sys.argv)

    widget = MSAgentWidget(
        acdPath=args.acd_path,
        animations=args.animations.split(","),
        scale=args.scale,
        volume=args.volume,
        cycles=args.cycles,
        speed=args.speed,
    )

    window = QMainWindow()
    window.setWindowTitle("MS Agent Player")
    window.setAttribute(Qt.WA_TranslucentBackground)
    window.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
    window.setCentralWidget(widget)
    window.show()

    widget.animationFinished.connect(qapp.quit)
    widget.start()

    signal.signal(signal.SIGINT, signal.SIG_DFL)
    sys.exit(qapp.exec())


if __name__ == "__main__":
    main()