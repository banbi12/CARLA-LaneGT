LEGACY_VERSION = 'semantic_v4_3_xodr_v42_base'
STRUCTURAL_VERSION = 'semantic_v4_5_xodr_structure_semantic_connections'
VERSION = STRUCTURAL_VERSION + '+boundary_route_xodr_aligned_trial_v2'
DISPLAY_NAME = 'semantic V4.5 R3 + XODR-aligned boundary v2'


def algorithm_version(policy):
    """Keep review identity tied to the selected geometry, including old policies."""
    if not policy.get('boundary_route_enabled', False):
        return STRUCTURAL_VERSION
    if policy.get('boundary_route_align_to_xodr', False):
        return VERSION
    return STRUCTURAL_VERSION + '+boundary_route_trial_v1'
