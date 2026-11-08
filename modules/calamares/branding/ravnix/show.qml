import QtQuick 2.0;
import calamares.slideshow 1.0;

// The slideshow of the RAVNIX graphical installer, shown while the system is
// installed. It is the same artwork as the rest of the distribution.
Presentation
{
    id: presentation

    function nextSlide() {
        presentation.goToNextSlide();
    }

    Timer {
        id: advanceTimer
        interval: 20000
        running: presentation.activatedInCalamares
        repeat: true
        onTriggered: nextSlide()
    }

    Slide {
        Text {
            anchors.centerIn: parent
            text: "One desktop"
            font.pixelSize: 30
            wrapMode: Text.WordWrap
            width: presentation.width
            horizontalAlignment: Text.Center
            color: "#f5a3c7"
        }
        Image {
            id: logo
            source: "ravnix-logo.png"
            width: 200; height: 200
            fillMode: Image.PreserveAspectFit
            anchors.bottom: title1.top
            anchors.horizontalCenter: parent.horizontalCenter
        }
        Text {
            id: title1
            anchors.horizontalCenter: logo.horizontalCenter
            anchors.top: logo.bottom
            text: "The graphical and the text installer write<br/>"+
                  "the <b>same RAVNIX configuration</b>, so the machine<br/>"+
                  "ends with the Purple Neon theme, the wallpaper,<br/>"+
                  "Fish, Brave Origin and the branded bootloader."
            wrapMode: Text.WordWrap
            width: presentation.width
            horizontalAlignment: Text.Center
            color: "#f5f0ff"
        }
    }

    Slide {
        Text {
            anchors.centerIn: parent
            text: "Offline by design"
            font.pixelSize: 30
            wrapMode: Text.WordWrap
            width: presentation.width
            horizontalAlignment: Text.Center
            color: "#a6f28a"
        }
        Image {
            id: background
            source: "ravnix-background.jpg"
            width: 320; height: 208
            fillMode: Image.PreserveAspectFit
            anchors.bottom: title2.top
            anchors.horizontalCenter: parent.horizontalCenter
        }
        Text {
            id: title2
            anchors.horizontalCenter: background.horizontalCenter
            anchors.top: background.bottom
            text: "The medium already carries the whole desktop,<br/>"+
                  "the bootloader and the pinned Nixpkgs source,<br/>"+
                  "so the installation downloads <b>nothing</b> and<br/>"+
                  "works without a network connection."
            wrapMode: Text.WordWrap
            width: presentation.width
            horizontalAlignment: Text.Center
            color: "#f5f0ff"
        }
    }

    Slide {
        Text {
            anchors.centerIn: parent
            text: "Reproducible"
            font.pixelSize: 30
            wrapMode: Text.WordWrap
            width: presentation.width
            horizontalAlignment: Text.Center
            color: "#b394c4"
        }
        Image {
            id: welcome
            source: "ravnix-welcome.png"
            width: 320; height: 240
            fillMode: Image.PreserveAspectFit
            anchors.bottom: title3.top
            anchors.horizontalCenter: parent.horizontalCenter
        }
        Text {
            id: title3
            anchors.horizontalCenter: welcome.horizontalCenter
            anchors.top: welcome.bottom
            text: "The Nixpkgs revision is pinned, so every machine<br/>"+
                  "gets the <b>same packages</b>, and a rebuild of the<br/>"+
                  "configuration needs neither the internet nor a<br/>"+
                  "GitHub account."
            wrapMode: Text.WordWrap
            width: presentation.width
            horizontalAlignment: Text.Center
            color: "#f5f0ff"
        }
    }

    function onActivate() {
        presentation.currentSlide = 0;
    }

    function onLeave() {
    }
}
