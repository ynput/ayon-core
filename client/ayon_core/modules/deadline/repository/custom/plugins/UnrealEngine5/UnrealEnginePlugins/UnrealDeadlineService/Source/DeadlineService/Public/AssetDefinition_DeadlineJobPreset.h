// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "DeadlineJobPreset.h"
#include "AssetDefinitionDefault.h"

#include "AssetDefinition_DeadlineJobPreset.generated.h"

UCLASS()
class UAssetDefinition_DeadlineJobPreset : public UAssetDefinitionDefault
{
	GENERATED_BODY()

public:
	// UAssetDefinition Begin
	virtual FText GetAssetDisplayName() const override { return NSLOCTEXT("AssetTypeActions", "AssetTypeActions_DeadlineJobPreset", "Deadline Job Preset"); }
	virtual FLinearColor GetAssetColor() const override { return FLinearColor::Red; }
	virtual TSoftClassPtr<UObject> GetAssetClass() const override { return UDeadlineJobPreset::StaticClass(); }
	virtual TConstArrayView<FAssetCategoryPath> GetAssetCategories() const override
	{
		static const auto Categories = { EAssetCategoryPaths::Misc };
		return Categories;
	}
	// UAssetDefinition End
};
