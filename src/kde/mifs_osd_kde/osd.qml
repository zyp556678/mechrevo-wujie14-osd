// The OSD surface itself.
//
// Three things here are load-bearing and easy to break by accident:
//
//  * The module is imported under an alias. `org.kde.layershell` exports its
//    attached type as plain `Window`, which would shadow QtQuick's `Window`
//    type -- and the layershell one is not creatable, so the component fails
//    to build with a bare "Type cannot be created in QML".
//  * The window is mapped once and never unmapped; only the image fades.
//    Mapping and unmapping a layer surface makes the compositor redo the
//    whole layer arrangement, and on Plasma that shows up as a flicker.
//  * input is transparent and the surface never takes the keyboard, so an OSD
//    that appears under the cursor cannot swallow a click.
import QtQuick
import org.kde.layershell as LS

Window {
    id: root

    visible: true
    color: "transparent"
    flags: Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus

    // LayerOverlay draws above panels and normal windows, which is what makes
    // this a real OSD. exclusionZone -1 means "reserve no space": the OSD must
    // never push other windows around or shrink the usable work area.
    LS.Window.layer: LS.Window.LayerOverlay
    LS.Window.keyboardInteractivity: LS.Window.KeyboardInteractivityNone
    LS.Window.exclusionZone: -1
    LS.Window.anchors: (osd.state.anchorLeft ? LS.Window.AnchorLeft
                                             : LS.Window.AnchorRight)
                     | (osd.state.anchorTop ? LS.Window.AnchorTop
                                            : LS.Window.AnchorBottom)
    LS.Window.margins.left: osd.state.marginLeft
    LS.Window.margins.right: osd.state.marginRight
    LS.Window.margins.top: osd.state.marginTop
    LS.Window.margins.bottom: osd.state.marginBottom

    width: osd.state.size
    height: osd.state.size

    Image {
        id: icon

        anchors.fill: parent
        source: osd.state.iconSource
        fillMode: Image.PreserveAspectFit
        smooth: true
        opacity: 0

        // Timings match the GNOME frontend and the vendor's Windows tool, so
        // the OSD feels the same whichever desktop is running.
        SequentialAnimation {
            id: pulse

            NumberAnimation {
                target: icon; property: "opacity"; to: 1
                duration: 120; easing.type: Easing.OutQuad
            }
            PauseAnimation { duration: 1500 }
            NumberAnimation {
                target: icon; property: "opacity"; to: 0
                duration: 250; easing.type: Easing.InQuad
            }
        }

        // The counter, not the icon name, is what re-triggers the animation:
        // pressing the same Fn key twice must show the OSD twice. `shown`
        // fires after the icon binding above has settled, never before.
        Connections {
            target: osd
            function onShown() { pulse.restart() }
        }
    }
}
