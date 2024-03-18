// Copyright Epic Games, Inc. All Rights Reserved.

#include "MoviePipelineDeadlineExecutorJobCustomization.h"

#include "DetailCategoryBuilder.h"
#include "DetailLayoutBuilder.h"

TSharedRef<IDetailCustomization> FMoviePipelineDeadlineExecutorJobCustomization::MakeInstance()
{
	return MakeShared<FMoviePipelineDeadlineExecutorJobCustomization>();
}

void FMoviePipelineDeadlineExecutorJobCustomization::CustomizeDetails(IDetailLayoutBuilder& DetailBuilder)
{
	IDetailCategoryBuilder& MrpCategory = DetailBuilder.EditCategory("Movie Render Pipeline");

	TArray<TSharedRef<IPropertyHandle>> OutMrpCategoryProperties;
	MrpCategory.GetDefaultProperties(OutMrpCategoryProperties);

	// We hide these properties because we want to use "Name", "UserName" and "Comment" from the Deadline preset
	const TArray<FName> PropertiesToHide = {"JobName", "Author"};

	for (const TSharedRef<IPropertyHandle>& PropertyHandle : OutMrpCategoryProperties)
	{
		if (PropertiesToHide.Contains(PropertyHandle->GetProperty()->GetFName()))
		{
			PropertyHandle->MarkHiddenByCustomization();
		}
	}
}
