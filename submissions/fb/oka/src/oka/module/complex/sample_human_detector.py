from typing import Optional, cast

from rcrscore.entities import Civilian, Entity, EntityID, Human
from rcrscore.urn import EntityURN

from adf_core_python.core.agent.develop.develop_data import DevelopData
from adf_core_python.core.agent.info.agent_info import AgentInfo
from adf_core_python.core.agent.info.scenario_info import ScenarioInfo
from adf_core_python.core.agent.info.world_info import WorldInfo
from adf_core_python.core.agent.module.module_manager import ModuleManager
from adf_core_python.core.component.module.algorithm.clustering import Clustering
from adf_core_python.core.component.module.complex.human_detector import HumanDetector
from adf_core_python.core.logger.logger import get_agent_logger


class SampleHumanDetector(HumanDetector):
  def __init__(
    self,
    agent_info: AgentInfo,
    world_info: WorldInfo,
    scenario_info: ScenarioInfo,
    module_manager: ModuleManager,
    develop_data: DevelopData,
  ) -> None:
    super().__init__(
      agent_info, world_info, scenario_info, module_manager, develop_data
    )
    self._clustering: Clustering = cast(
      Clustering,
      module_manager.get_module(
        "oka.HumanDetector.Clustering",
        "adf_core_python.implement.module.algorithm.k_means_clustering.KMeansClustering",
      ),
    )
    self.register_sub_module(self._clustering)

    self._result: Optional[EntityID] = None
    self._logger = get_agent_logger(
      f"{self.__class__.__module__}.{self.__class__.__qualname__}",
      self._agent_info,
    )

  def calculate(self) -> HumanDetector:
    transport_human: Optional[Human] = self._agent_info.some_one_on_board()
    if transport_human is not None:
      self._result = transport_human.get_entity_id()
      return self

    if self._result is not None:
      if not self._is_valid_human(self._result):
        self._result = None

    self._result = self._select_target()
    return self

  def _calculate_target_score(self, entity: Entity) -> float:
    distance = self._world_info.get_distance(
      self._agent_info.get_entity_id(),
      entity.get_entity_id(),
    )
    hp = entity.get_hp()
    damage = entity.get_damage()
    
    time_to_death = hp / damage if damage is not None and damage > 0 else float('inf')
    
    # 距離が近く、死期が近いほどスコアを小さく（優先度を高く）する
    alpha = 1.0
    beta = 50.0 
    return (alpha * distance) + (beta * time_to_death)
  
  def _select_target(self) -> Optional[EntityID]:
    #if self._result is not None and self._is_valid_human(self._result):
    #  return self._result

    cluster_index: int = self._clustering.get_cluster_index(
      self._agent_info.get_entity_id()
    )
    cluster_entities: list[Entity] = self._clustering.get_cluster_entities(
      cluster_index
    )

    # --- クラスタ内の探索 ---
    cluster_valid_human_entities: list[Entity] = [
      entity
      for entity in cluster_entities
      if self._is_valid_human(entity.get_entity_id()) and isinstance(entity, Civilian)
    ]
    if len(cluster_valid_human_entities) != 0:
      best_target = cluster_valid_human_entities[0]
      best_score = self._calculate_target_score(best_target)
      
      for entity in cluster_valid_human_entities:
        score = self._calculate_target_score(entity)
        if score < best_score:
          best_score = score
          best_target = entity
      return best_target.get_entity_id()

    # --- ワールド全体の探索 ---
    world_valid_human_entities: list[Entity] = [
      entity
      for entity in self._world_info.get_entities_of_types([Civilian])
      if self._is_valid_human(entity.get_entity_id())
    ]
    if len(world_valid_human_entities) != 0:
      best_target = world_valid_human_entities[0]
      best_score = self._calculate_target_score(best_target)
      
      for entity in world_valid_human_entities:
        score = self._calculate_target_score(entity)
        if score < best_score:
          best_score = score
          best_target = entity
      return best_target.get_entity_id()

    return None

  def _is_valid_human(self, target_entity_id: EntityID) -> bool:
    target: Optional[Entity] = self._world_info.get_entity(target_entity_id)
    if target is None:
      return False
    if not isinstance(target, Human):
      return False
    hp: Optional[int] = target.get_hp()
    if hp is None or hp <= 0:
      return False
    buriedness: Optional[int] = target.get_buriedness()
    if buriedness is None:
      return False
    myself = self._agent_info.get_myself()
    if myself is None:
      return False
    if myself.get_urn() == EntityURN.FIRE_BRIGADE and buriedness == 0:
      return False
    if myself.get_urn() == EntityURN.AMBULANCE_TEAM and buriedness > 0:
      return False
    damage: Optional[int] = target.get_damage()
    if damage is None or damage == 0:
      return False
    position_entity_id: Optional[EntityID] = target.get_position()
    if position_entity_id is None:
      return False
    position: Optional[Entity] = self._world_info.get_entity(position_entity_id)
    if position is None:
      return False
    urn: EntityURN = position.get_urn()
    if urn == EntityURN.REFUGE or urn == EntityURN.AMBULANCE_TEAM:
      return False

    return True

  def get_target_entity_id(self) -> Optional[EntityID]:
    return self._result
