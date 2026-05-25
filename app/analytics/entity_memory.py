"""
Entity Memory - Persistent storage for learned entities
"""

import json
import os
from datetime import datetime


class EntityMemory:
    """Store and retrieve learned entity categorizations"""

    def __init__(self, storage_path='data/entity_memory.json'):
        self.storage_path = storage_path
        self.memory = self._load()

    def _load(self):
        """Load memory from disk"""
        if os.path.exists(self.storage_path):
            with open(self.storage_path, 'r') as f:
                return json.load(f)
        return {}

    def _save(self):
        """Save memory to disk"""
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        with open(self.storage_path, 'w') as f:
            json.dump(self.memory, f, indent=2)

    def get(self, entity_name):
        """Get stored category for entity"""
        return self.memory.get(entity_name)

    def store(self, entity_name, category, entity_type, source='auto'):
        """Store entity categorization"""
        existing = self.memory.get(entity_name, {})

        # Don't override user corrections with auto categorization
        if existing.get('source') == 'user' and source == 'auto':
            return

        self.memory[entity_name] = {
            'category': category,
            'entity_type': entity_type,
            'source': source,  # 'auto' or 'user'
            'last_seen': datetime.now().isoformat(),
            'count': existing.get('count', 0) + 1
        }
        self._save()

    def bulk_store(self, entities):
        """Store multiple entities at once"""
        for entity_name, data in entities.items():
            source = data.get('source', 'auto')
            self.store(entity_name, data['category'], data['entity_type'], source)

    def get_stats(self):
        """Get memory statistics"""
        return {
            'total_entities': len(self.memory),
            'platforms': len([e for e in self.memory.values() if e['entity_type'] == 'platform']),
            'persons': len([e for e in self.memory.values() if e['entity_type'] == 'person']),
            'merchants': len([e for e in self.memory.values() if e['entity_type'] == 'merchant'])
        }