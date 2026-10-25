from typing import Optional, cast

from rcrscore.entities import AmbulanceTeam, Building, Entity, EntityID, Human, Refuge

from adf_core_python.core.agent.communication.message_manager import MessageManager
from adf_core_python.core.agent.develop.develop_data import DevelopData
from adf_core_python.core.agent.info.agent_info import AgentInfo
from adf_core_python.core.agent.info.scenario_info import ScenarioInfo
from adf_core_python.core.agent.info.world_info import WorldInfo
from adf_core_python.core.agent.module.module_manager import ModuleManager
from adf_core_python.core.component.module.algorithm.clustering import Clustering
from adf_core_python.core.component.module.algorithm.path_planning import PathPlanning
from adf_core_python.core.component.module.complex.search import Search
from adf_core_python.core.logger.logger import get_agent_logger


class SampleSearch(Search):
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

    self._unreached_building_ids: set[EntityID] = set()
    self._unreachable_building_ids: set[EntityID] = set()
    self._result: Optional[EntityID] = None

    self._last_position_id: Optional[EntityID] = None
    self._stuck_count: int = 0
    self._cluster_offset: int = 0

    self._clustering: Clustering = cast(
      Clustering,
      module_manager.get_module(
        "oka.Search.Clustering",
        "adf_core_python.implement.module.algorithm.k_means_clustering.KMeansClustering",
      ),
    )

    self._path_planning: PathPlanning = cast(
      PathPlanning,
      module_manager.get_module(
        "oka.Search.PathPlanning",
        "src.camp_default_2026.cached_path_planning.CachedPathPlanning",
      ),
    )

    self._logger = get_agent_logger(
      f"{self.__class__.__module__}.{self.__class__.__qualname__}",
      self._agent_info,
    )

    self.register_sub_module(self._clustering)
    self.register_sub_module(self._path_planning)

  def update_info(self, message_manager: MessageManager) -> Search:
    super().update_info(message_manager)
    if self.get_count_update_info() > 1:
      return self

    current_pos_id = self._agent_info.get_position_entity_id()
    if current_pos_id is not None:
      self._unreached_building_ids.discard(current_pos_id)

    # 視界に入って「壊れていない（brokenness == 0）」と判明した建物を即座に除外する
    for b_id in list(self._unreached_building_ids):
      entity = self._world_info.get_entity(b_id)
      if isinstance(entity, Building):
        brokenness = entity.get_brokenness()
        if brokenness is not None and brokenness == 0:
          self._unreached_building_ids.discard(b_id)

    # スタック判定：目的地に着いていないのに3ステップ同じ場所ならブラックリストへ
    if (
      self._result is not None
      and current_pos_id != self._result
      and current_pos_id == self._last_position_id
    ):
      self._stuck_count += 1
      if self._stuck_count >= 3:
        self._unreached_building_ids.discard(self._result)
        self._unreachable_building_ids.add(self._result)
        self._stuck_count = 0
    else:
      self._last_position_id = current_pos_id
      self._stuck_count = 0

    # 未探索リストが空になったら補充（空なら隣のクラスタへ）
    if len(self._unreached_building_ids) == 0:
      for _ in range(5):  # 最大5クラスタ先まで探す
        targets = self._get_search_targets()
        self._unreached_building_ids = targets - self._unreachable_building_ids
        if len(self._unreached_building_ids) > 0:
          break
        self._cluster_offset += 1

      # それでも空ならブラックリストをリセット
      if len(self._unreached_building_ids) == 0:
        self._unreachable_building_ids.clear()
        self._unreached_building_ids = self._get_search_targets()

    return self

  def calculate(self) -> Search:
    position = self._agent_info.get_position_entity_id()
    if position is None:
      self._result = None
      return self

    # 知っている全エンティティから「人が埋まっている建物」を特定する
    ambulance_buildings: set[EntityID] = set()
    human_buildings: set[EntityID] = set()

    for entity in self._world_info.get_entities():
      if isinstance(entity, Human):
        hp = entity.get_hp()
        buriedness = entity.get_buriedness()
        pos_id = entity.get_position()
        # 生存していて瓦礫に埋まっている場合
        if (
          hp is not None
          and hp > 0
          and buriedness is not None
          and buriedness > 0
          and pos_id is not None
        ):
          if isinstance(entity, AmbulanceTeam):
            ambulance_buildings.add(pos_id)
          else:
            human_buildings.add(pos_id)

    nearest_building_id: Optional[EntityID] = None
    best_score = float("inf")

    for building_id in list(self._unreached_building_ids):
      distance = self._path_planning.get_distance(position, building_id)
      if distance == float("inf") or distance < 0:
        continue

      score = float(distance)

      # 1. 救急隊が埋まっている建物は超最優先（距離を1/100として扱う）
      if building_id in ambulance_buildings:
        score *= 0.01
      # 2. 市民や他の味方が埋まっている建物も最優先（距離を1/20として扱う）
      elif building_id in human_buildings:
        score *= 0.05
      else:
        # 3. 人が見えているか不明な場合は、建物の倒壊度が大きいほど優先する
        entity = self._world_info.get_entity(building_id)
        if isinstance(entity, Building):
          brokenness = entity.get_brokenness()
          if brokenness is not None and brokenness > 0:
            # 倒壊度が大きいほど係数を小さくする（0.5〜0.8倍）
            score *= max(0.5, 0.9 - (brokenness * 0.005))

      if score < best_score:
        nearest_building_id = building_id
        best_score = score

    self._result = nearest_building_id
    return self

  def get_target_entity_id(self) -> Optional[EntityID]:
    return self._result

  def _get_search_targets(self) -> set[EntityID]:
    base_index: int = self._clustering.get_cluster_index(
      self._agent_info.get_entity_id()
    )
    cluster_num: int = self._clustering.get_cluster_number()

    if cluster_num > 0:
      target_index = (base_index + self._cluster_offset) % cluster_num
    else:
      target_index = base_index

    cluster_entities: list[Entity] = self._clustering.get_cluster_entities(
      target_index
    )

    building_entity_ids: list[EntityID] = []
    for entity in cluster_entities:
      if isinstance(entity, Building) and not isinstance(entity, Refuge):
        brokenness = entity.get_brokenness()
        if brokenness is not None and brokenness == 0:
          continue
        building_entity_ids.append(entity.get_entity_id())

    return set(building_entity_ids)