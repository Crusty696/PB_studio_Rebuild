import os
import yaml
import networkx as nx
import pyqtgraph as pg
import numpy as np
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, 
    QTableWidget, QTableWidgetItem, QHeaderView, QSlider, QLabel, 
    QPushButton, QGroupBox, QFormLayout, QSplitter, QScrollArea
)
from PySide6.QtCore import Qt, Signal, Slot
from sqlalchemy.orm import Session
from database import engine
from database.models import (
    StructStyleBucket, StructCompatEdge, MemLearnedPattern, 
    MemDecision, MemPacingRun
)
from sqlalchemy import desc

class StructureTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        
        # Splitter for Graph and Stats
        self.splitter = QSplitter(Qt.Horizontal)
        
        # Graph View
        self.graph_container = QWidget()
        self.graph_layout = QVBoxLayout(self.graph_container)
        self.graph_view = pg.GraphicsLayoutWidget()
        self.plot = self.graph_view.addPlot()
        self.plot.setAspectLocked()
        self.plot.hideAxis('bottom')
        self.plot.hideAxis('left')
        self.graph_layout.addWidget(self.graph_view)
        
        # Stats / Inspector
        self.inspector = QGroupBox("Stats Inspector")
        self.inspector_layout = QFormLayout(self.inspector)
        self.bucket_count_label = QLabel("0")
        self.edge_count_label = QLabel("0")
        self.inspector_layout.addRow("Style Buckets:", self.bucket_count_label)
        self.inspector_layout.addRow("Compat Edges:", self.edge_count_label)
        
        # Refresh Button
        self.refresh_btn = QPushButton("Refresh Structure")
        self.refresh_btn.clicked.connect(self.refresh_data)
        self.inspector_layout.addRow(self.refresh_btn)

        self.splitter.addWidget(self.graph_container)
        self.splitter.addWidget(self.inspector)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)
        
        self.layout.addWidget(self.splitter)
        
        self.graph_item = pg.GraphItem()
        self.plot.addItem(self.graph_item)
        
    def refresh_data(self):
        with Session(engine) as session:
            buckets = session.query(StructStyleBucket).all()
            edges = session.query(StructCompatEdge).all()
            
            self.bucket_count_label.setText(str(len(buckets)))
            self.edge_count_label.setText(str(len(edges)))
            
            # Build NetworkX graph for layout
            G = nx.Graph()
            for b in buckets:
                G.add_node(b.id, name=b.name)
            for e in edges:
                G.add_edge(e.scene_id_a, e.scene_id_b, weight=e.cosine_similarity)
            
            if len(buckets) > 0:
                pos = nx.spring_layout(G)
                
                # Convert pos to numpy array for pyqtgraph
                nodes = np.array(list(G.nodes()))
                adj = np.array(list(G.edges()))
                
                # Prepare node positions
                node_pos = np.array([pos[n] for n in nodes])
                
                # Update graph item
                self.graph_item.setData(pos=node_pos, adj=adj, symbol='o', size=10, pen='w')
                
class MemoryTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["ID", "Type", "Confidence", "Last Updated"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        
        self.refresh_btn = QPushButton("Refresh Patterns")
        self.refresh_btn.clicked.connect(self.refresh_data)
        
        self.layout.addWidget(self.table)
        self.layout.addWidget(self.refresh_btn)
        
    def refresh_data(self):
        with Session(engine) as session:
            patterns = session.query(MemLearnedPattern).order_by(desc(MemLearnedPattern.confidence)).all()
            self.table.setRowCount(len(patterns))
            for i, p in enumerate(patterns):
                self.table.setItem(i, 0, QTableWidgetItem(str(p.id)))
                self.table.setItem(i, 1, QTableWidgetItem(str(p.pattern_type)))
                self.table.setItem(i, 2, QTableWidgetItem(f"{p.confidence:.3f}"))
                self.table.setItem(i, 3, QTableWidgetItem(str(p.last_updated)))

class AuditTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["ID", "Run ID", "Scene ID", "Score", "Verdict"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        
        self.refresh_btn = QPushButton("Refresh Audit Logs")
        self.refresh_btn.clicked.connect(self.refresh_data)
        
        self.layout.addWidget(self.table)
        self.layout.addWidget(self.refresh_btn)
        
    def refresh_data(self):
        with Session(engine) as session:
            decisions = session.query(MemDecision).order_by(desc(MemDecision.id)).limit(100).all()
            self.table.setRowCount(len(decisions))
            for i, d in enumerate(decisions):
                self.table.setItem(i, 0, QTableWidgetItem(str(d.id)))
                self.table.setItem(i, 1, QTableWidgetItem(str(d.run_id)))
                self.table.setItem(i, 2, QTableWidgetItem(str(d.scene_id)))
                self.table.setItem(i, 3, QTableWidgetItem(f"{d.agent_score:.3f}"))
                self.table.setItem(i, 4, QTableWidgetItem(str(d.user_verdict or "N/A")))

class SteerTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.config_path = os.path.join("config", "pacing_weights.yaml")
        
        self.scroll = QScrollArea()
        self.scroll_content = QWidget()
        self.form_layout = QFormLayout(self.scroll_content)
        self.sliders = {}
        
        self.load_weights()
        
        self.scroll.setWidget(self.scroll_content)
        self.scroll.setWidgetResizable(True)
        self.layout.addWidget(self.scroll)
        
        self.save_btn = QPushButton("Save Weights")
        self.save_btn.clicked.connect(self.save_weights)
        self.layout.addWidget(self.save_btn)
        
    def load_weights(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, "r") as f:
                data = yaml.safe_load(f)
                weights = data.get("weights", {})
                for key, val in weights.items():
                    slider = QSlider(Qt.Horizontal)
                    slider.setRange(0, 100)
                    slider.setValue(int(val * 100))
                    label = QLabel(f"{val:.2f}")
                    slider.valueChanged.connect(lambda v, l=label: l.setText(f"{v/100:.2f}"))
                    
                    row_widget = QWidget()
                    row_layout = QHBoxLayout(row_widget)
                    row_layout.addWidget(slider)
                    row_layout.addWidget(label)
                    
                    self.form_layout.addRow(key, row_widget)
                    self.sliders[key] = slider

    def save_weights(self):
        weights = {key: slider.value() / 100.0 for key, slider in self.sliders.items()}
        data = {"weights": weights}
        with open(self.config_path, "w") as f:
            yaml.dump(data, f)
        print(f"Weights saved to {self.config_path}")

class StudioBrainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Studio Brain — Director's Cockpit")
        self.resize(1000, 700)
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        
        self.tabs = QTabWidget()
        self.tabs.addTab(StructureTab(), "Structure")
        self.tabs.addTab(MemoryTab(), "Memory")
        self.tabs.addTab(AuditTab(), "Audit")
        self.tabs.addTab(SteerTab(), "Steer")
        
        self.layout.addWidget(self.tabs)

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    import sys
    app = QApplication(sys.argv)
    window = StudioBrainWindow()
    window.show()
    sys.exit(app.exec())
