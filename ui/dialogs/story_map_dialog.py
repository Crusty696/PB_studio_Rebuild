import pyqtgraph as pg
import numpy as np
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGroupBox
)
from PySide6.QtCore import Qt
from database.session import nullpool_session
from database.models import MemPacingRun, MemDecision, Scene

class StoryMapDialog(QDialog):
    def __init__(self, run_id, parent=None):
        super().__init__(parent)
        self.run_id = run_id
        self.setWindowTitle(f"Story Map — Pacing Run #{run_id}")
        self.resize(800, 400)
        
        self.layout = QVBoxLayout(self)
        
        # Plot Widget
        self.plot_widget = pg.PlotWidget(title="Energy Arc: Intended vs. Realized")
        self.plot_widget.addLegend()
        self.plot_widget.setLabel('left', 'Energy', units='0.0-1.0')
        self.plot_widget.setLabel('bottom', 'Sequence Index')
        self.layout.addWidget(self.plot_widget)
        
        # Controls
        self.controls_layout = QHBoxLayout()
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        self.controls_layout.addStretch()
        self.controls_layout.addWidget(self.close_btn)
        self.layout.addLayout(self.controls_layout)
        
        self.load_and_plot()
        
    def load_and_plot(self):
        with nullpool_session() as session:
            run = session.query(MemPacingRun).filter(MemPacingRun.id == self.run_id).first()
            if not run:
                print(f"Run {self.run_id} not found")
                return
            
            decisions = session.query(MemDecision).filter(
                MemDecision.run_id == self.run_id
            ).order_by(MemDecision.sequence_idx).all()
            
            if not decisions:
                return
            
            indices = [d.sequence_idx for d in decisions]
            intended_energy = [d.at_energy or 0.0 for d in decisions]
            
            # For realized energy, we take the scene energy if available
            realized_energy = []
            for d in decisions:
                scene = session.query(Scene).filter(Scene.id == d.scene_id).first()
                realized_energy.append(scene.energy if scene and scene.energy else 0.0)
            
            # Plotting
            self.plot_widget.plot(
                indices, intended_energy, 
                pen=pg.mkPen('b', width=2), 
                name="Intended (Audio/Blueprint)"
            )
            self.plot_widget.plot(
                indices, realized_energy, 
                pen=pg.mkPen('r', width=2, style=Qt.DashLine), 
                name="Realized (Video Scenes)"
            )
            
            # Add a vertical fill/difference would be cool but keep it simple for now
            
if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    import sys
    app = QApplication(sys.argv)
    # Mock run_id for testing
    dialog = StoryMapDialog(run_id=1)
    dialog.show()
    sys.exit(app.exec())
